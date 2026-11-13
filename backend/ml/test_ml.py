import numpy as np
import pandas as pd
import pytest

from ingestion.test_ingestion import ORDERS, SHIPMENTS, client, run  # noqa: F401
from ml import features
from ml.features import CATEGORICAL, NUMERIC, address_features, design_matrix, time_aware_history
from ml.models import RiskModel
from ml.train import TRAIN_SHARE, VALID_SHARE, economics, fit

UTC = lambda s: pd.Timestamp(s, tz="UTC")   # noqa: E731


def synthetic(n=3000, seed=7):
    """Fake parcels where COD, new customers and thin addresses raise RTO."""
    r = np.random.default_rng(seed)

    d = pd.DataFrame(
        {c: 0.0 for c in features.NUMERIC},
        index=range(n),
    )

    d["is_cod"] = r.integers(0, 2, n)
    d["repeat_orders"] = r.integers(0, 6, n)
    d["addr_commas"] = r.integers(0, 5, n)
    d["order_value"] = r.integers(300, 4000, n).astype(float)

    d["zone"] = r.choice(list("ABC"), n)
    d["sales_channel"] = r.choice(["Website", "WhatsApp"], n)

    z = (
        -1.5
        + 2.2 * d.is_cod
        - 0.35 * d.repeat_orders
        - 0.5 * d.addr_commas
    )

    d["is_rto"] = (
        r.random(n) < 1 / (1 + np.exp(-z))
    ).astype(int)

    d["order_ts"] = pd.date_range(
        "2025-01-01",
        periods=n,
        freq="h",
        tz="UTC",
    )

    d["billed_total_inr"] = 400.0

    return d


def test_no_future_or_leaky_features():
    names = NUMERIC + CATEGORICAL
    leaky = ["courier", "deliver", "final_status", "pickup", "billed", "remit", "invoice", "ndr", "attempt",
             "is_rto", "is_lost", "on_time", "days_", "weight", "cod_due"]
    assert not [f for f in names if any(word in f for word in leaky)]
    X = design_matrix(synthetic(50))
    assert "billed_total_inr" not in X.columns and "is_rto" not in X.columns
    assert not [c for c in X.columns if c.startswith("courier")]


def test_history_counts_only_outcomes_known_before_the_order():
    d = pd.DataFrame([
        # customer 1, order placed 1 Mar, came back; the return was known on 5 Mar
        dict(customer_id=1, pincode="411001", order_ts=UTC("2025-03-01"), resolved_ts=UTC("2025-03-05"), is_rto=1),
        # placed at exactly the moment that return became known: must not see it yet
        dict(customer_id=1, pincode="411001", order_ts=UTC("2025-03-05"), resolved_ts=pd.NaT, is_rto=0),
        # placed a day later: sees the return and the delivery known on 3 Mar
        dict(customer_id=1, pincode="411001", order_ts=UTC("2025-03-06"), resolved_ts=UTC("2025-03-09"), is_rto=0),
        # placed 2 Mar, delivered 3 Mar: before that delivery, nothing was known
        dict(customer_id=1, pincode="411001", order_ts=UTC("2025-03-02"), resolved_ts=UTC("2025-03-03"), is_rto=0),
        # no customer, no pincode: no history, no error
        dict(customer_id=None, pincode="", order_ts=UTC("2025-03-10"), resolved_ts=pd.NaT, is_rto=0),
    ], index=[10, 11, 12, 13, 14])

    h = time_aware_history(d)

    assert list(h.index) == [10, 11, 12, 13, 14]
    assert list(h.cust_prior_rto) == [0, 0, 1, 0, 0]
    assert list(h.cust_prior_delivered) == [0, 1, 1, 0, 0]
    assert list(h.pin_prior_parcels) == [0, 1, 2, 0, 0]
    assert h.pin_prior_rto_rate[10] == 0.2               # nothing known yet: the 0.2 fallback
    # merchant-wide rate so far: nothing known on 1 Mar; by 5 Mar only the 3 Mar delivery is known
    assert h.base_rto_rate[10] == 0.2 and h.base_rto_rate[11] == 0.0
    assert 0 < h.pin_prior_rto_rate[12] < 1


def test_address_features():
    a = address_features(pd.Series(["flat 2, fc road, near temple", "Ganesh Society, FC Road, Opp. SBI ATM",
                                     None, "", "Plot 9, " + "x" * 150], index=[7, 8, 9, 10, 11]))

    assert list(a.columns) == ["addr_len", "addr_commas", "addr_has_number", "addr_has_landmark",
                               "addr_is_lowercase"]
    assert list(a.index) == [7, 8, 9, 10, 11]
    assert a.loc[7].tolist() == [28, 2, 1, 1, 1]
    assert a.loc[8].tolist() == [37, 2, 0, 1, 0]          # "Opp." counts as a landmark, any case
    assert a.loc[9].tolist() == a.loc[10].tolist() == [0, 0, 0, 0, 0]
    assert a.loc[11, "addr_len"] == 100                   # very long addresses are capped


def test_derive_caps_repeat_orders_and_smooths_the_customer_rate():
    d = pd.DataFrame({
        "payment_mode": ["COD", "COD", "Prepaid"],
        "order_value": [500.0] * 3,
        "order_hour": [1, 14, 14],
        "is_weekend": [0] * 3,
        "prior_orders": [0, 18, 2],
        "cust_prior_rto": [0, 6, 0],
        "cust_prior_delivered": [0, 12, 2],
        "base_rto_rate": [0.2] * 3,
        "pin_prior_rto_rate": [0.2] * 3,
        "city_tier": [1, None, 1],
        "address": ["home", "Flat 2, FC Road", ""],
    })

    out = features.derive(d)

    assert out.repeat_orders.tolist() == [0, 5, 2]
    assert out.cod_first_order.tolist() == [1, 0, 0]
    assert out.is_late_night.tolist() == [1, 0, 0]
    assert out.city_tier.tolist() == [1, 2, 1]

    assert out.cust_rto_rate.round(3).tolist() == [
        0.2, 0.314, 0.12
    ]


def test_design_matrix_handles_unseen_categories():
    columns = design_matrix(synthetic(200)).columns
    new = synthetic(3, seed=1)
    new["zone"] = ["Z", "", None]
    new["sales_channel"] = ["Marketplace", "Website", None]

    X = design_matrix(new, columns=columns)

    assert list(X.columns) == list(columns)
    assert not [c for c in X.columns if c.endswith("=Z") or c.endswith("=") or "Marketplace" in c]
    assert X[[c for c in columns if c.startswith("zone=")]].to_numpy().sum() == 0
    assert X.loc[1, "sales_channel=Website"] == 1
    assert not X.isna().any().any()


def test_training_on_synthetic_orders():
    d = synthetic()
    scorer, m, test = fit(d)

    # time split: oldest 70% train, next 15% validation, newest 15% test, no overlap
    split = m["split"]
    assert split["train"]["rows"] == int(len(d) * TRAIN_SHARE)
    assert split["valid"]["rows"] == int(len(d) * (TRAIN_SHARE + VALID_SHARE)) - split["train"]["rows"]
    assert split["train"]["to"] <= split["valid"]["from"] <= split["valid"]["to"] <= split["test"]["from"]
    assert test["order_ts"].min() >= d["order_ts"].iloc[split["train"]["rows"] + split["valid"]["rows"]]

    # chosen on validation AUC only, with LightGBM needing a margin
    c = m["candidates"]
    lgb_wins = c["lightgbm"]["valid"]["auc"] >= c["logistic"]["valid"]["auc"] + 0.005
    assert m["chosen"] == ("lightgbm" if lgb_wins else "logistic")
    assert m["lgb_best_iteration"] >= 1

    # calibrated probabilities and a model that learned something
    p = scorer.score(test)
    assert ((p > 0) & (p < 1)).all()
    assert m["test_after_calibration"]["auc"] > 0.6
    assert m["test_after_calibration"]["brier"] < m["brier_if_we_predicted_the_average"]
    assert sum(b["orders"] for b in m["bands"]) == len(test)

    # explanations line up with the features
    contrib = scorer.contributions(scorer.matrix(test.head(5)))
    assert contrib.shape == (5, len(scorer.columns))
    assert {f["feature"] for f in m["top_features"]} <= set(NUMERIC + CATEGORICAL)
    assert "billed_total_inr" not in scorer.columns


def test_economics():
    test = pd.DataFrame({
        "is_cod":      [1,    1,    1,    1,    0],
        "is_rto":      [1,    0,    1,    0,    1],
        "order_value": [1000, 2000, 500,  800,  900],
    })
    p = [0.9, 0.6, 0.2, 0.1, 0.99]       # the prepaid order is ignored however risky it looks

    e = economics(test, p, cost=100.0)

    assert e["cod_orders_in_test"] == 4 and e["cod_rto_in_test"] == 2 and e["cod_rto_cost_in_test_inr"] == 200
    row = next(r for r in e["table"] if r["threshold"] == 0.5)
    # flags the 0.9 RTO (saves 100) and the 0.6 good order (loses 2000 x 30% x (1 - 0.6) = 240)
    assert row == {"threshold": 0.5, "orders_flagged": 2, "rto_caught": 1, "good_orders_flagged": 1,
                   "saved_inr": 100, "margin_lost_inr": 240, "net_inr": -140}
    assert [r["threshold"] for r in e["table"]][0] == 0.1 and e["table"][-1]["threshold"] == 0.8
    assert e["best"]["threshold"] == 0.65 and e["best"]["net_inr"] == 100     # only the sure RTO flagged

    cheap = economics(test, p, cost=100.0, margin_pct=10, keep_rate=0.5)
    row = next(r for r in cheap["table"] if r["threshold"] == 0.5)
    assert row["margin_lost_inr"] == 100 and cheap["assumptions"] == {"rto_cost_inr": 100.0, "margin_pct": 10,
                                                                      "keep_rate": 0.5}


def test_small_merchant_gets_insufficient_data_and_no_economics(client):
    run(client, "orders", ORDERS)
    run(client, "shipments", SHIPMENTS)

    r = client.post("/api/ml/train/")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "insufficient_data" and body["is_active"] is False
    assert body["rows"] == 2 and "reason" in body

    assert client.get("/api/ml/model/").json()["id"] == body["id"]
    assert client.get("/api/ml/economics/").status_code == 404
    assert client.get("/api/ml/economics/?margin_pct=abc").status_code == 400
    assert client.get("/api/ml/economics/?keep_rate=2").status_code == 400
    assert not RiskModel.objects.for_merchant(client.merchant).filter(is_active=True).exists()


# ---------------------------------------------------------------- M5 step 2: risk bands and model compatibility
M4_COLUMNS = [   # what an M4 model was trained on (old features, no feature_version in its metrics)
    "is_cod", "order_value", "order_hour", "is_late_night", "is_weekend", "prior_orders", "is_first_order",
    "cust_prior_rto", "cust_prior_delivered", "pin_prior_parcels", "pin_prior_rto_rate", "city_tier",
    "addr_len", "addr_words", "addr_commas", "addr_has_number", "addr_has_landmark", "addr_is_lowercase",
    "zone=A", "zone=B", "zone=C", "zone=D", "zone=E",
    "sales_channel=Instagram Shop", "sales_channel=Website", "sales_channel=WhatsApp",
]


def m4_model(merchant):
    """An active model saved the way M4 saved it: old feature columns, M4 metrics, a joblib artifact."""
    import io

    import joblib
    from django.core.files.base import ContentFile

    from ml.train import Scorer
    old = Scorer("logistic", None, M4_COLUMNS)
    buf = io.BytesIO()
    joblib.dump({"scorer": old, "test": pd.DataFrame({"is_rto": [0, 1]}), "rto_cost": 442.12}, buf)
    run = RiskModel(merchant=merchant, status=RiskModel.Status.TRAINED, is_active=True,
                    metrics={"chosen": "logistic", "economics": {"best": None}, "bands": []})
    run.artifact.save("rto_m4.joblib", ContentFile(buf.getvalue()), save=True)
    return run


def test_risk_bands_are_separate_from_calibration_bands():
    from ml.train import BANDS, RISK_BANDS
    _, m, _ = fit(synthetic())

    assert m["risk_bands"] == RISK_BANDS == {"medium_from": 0.10, "high_from": 0.25, "very_high_from": 0.50}
    assert len(BANDS) == 6 and BANDS[0] == (0.00, 0.05, "0-5%")          # the calibration bins are untouched
    assert m["bands"] and all(set(b) == {"score_band", "orders", "avg_predicted", "actual_rto_rate"}
                              for b in m["bands"])


def test_cod_prepaid_threshold_comes_from_the_economics(monkeypatch):
    from ml import train
    _, m, _ = fit(synthetic())
    assert m["economics"]["best"] is not None
    assert m["cod_prepaid_threshold"] == m["economics"]["best"]["threshold"]

    real = train.economics
    monkeypatch.setattr(train, "economics", lambda *a, **k: {**real(*a, **k), "best": None})
    _, m, _ = fit(synthetic())
    assert m["cod_prepaid_threshold"] is None                            # no cut-off pays -> no threshold


def test_trained_metrics_record_the_ordered_feature_columns():
    scorer, m, _ = fit(synthetic())

    assert m["feature_version"] == 2
    assert m["feature_columns"] == scorer.columns
    assert m["feature_columns"][:len(NUMERIC)] == NUMERIC                 # numbers first, in order
    assert [c for c in m["feature_columns"][len(NUMERIC):]] == ["zone=A", "zone=B", "zone=C",
                                                               "sales_channel=Website", "sales_channel=WhatsApp"]


def test_m4_model_metadata_is_detected_as_stale():
    from ml.train import model_feature_compatible
    _, m, _ = fit(synthetic())
    current = RiskModel(status=RiskModel.Status.TRAINED, metrics=m)
    assert model_feature_compatible(current) is True

    m4 = RiskModel(status=RiskModel.Status.TRAINED, metrics={"chosen": "logistic"})       # no version, no columns
    m4_columns_v2 = RiskModel(status=RiskModel.Status.TRAINED,                            # old columns, new label
                              metrics={"feature_version": 2, "feature_columns": M4_COLUMNS})
    reordered = RiskModel(status=RiskModel.Status.TRAINED,
                          metrics={**m, "feature_columns": m["feature_columns"][::-1]})
    underscore = RiskModel(status=RiskModel.Status.TRAINED,
                           metrics={**m, "feature_columns": [c.replace("=", "_") for c in m["feature_columns"]]})
    weak = RiskModel(status=RiskModel.Status.INSUFFICIENT_DATA, metrics=m)
    assert not any(model_feature_compatible(r) for r in [m4, m4_columns_v2, reordered, underscore, weak])


def test_m4_artifacts_still_load(client):  # noqa: F811
    from ml.train import Scorer, load_artifact, model_feature_compatible
    run = m4_model(client.merchant)

    saved = load_artifact(run)
    assert set(saved) == {"scorer", "test", "rto_cost"}
    assert isinstance(saved["scorer"], Scorer) and saved["scorer"].columns == M4_COLUMNS
    assert model_feature_compatible(run) is False


def test_economics_api_refuses_a_stale_model_with_409(client):  # noqa: F811
    m4_model(client.merchant)

    r = client.get("/api/ml/economics/")
    assert r.status_code == 409
    assert r.json() == {"error": "This model was trained with an older feature set.",
                        "action": "POST /api/ml/train/ to retrain the model."}
    assert client.get("/api/ml/economics/?margin_pct=50&keep_rate=0.2").status_code == 409
    assert client.get("/api/ml/economics/?margin_pct=abc").status_code == 400     # bad input still a 400


def test_economics_api_unchanged_for_a_current_model(client, monkeypatch):  # noqa: F811
    from ml import train
    monkeypatch.setattr(train, "training_frame", lambda m: synthetic())
    run = client.post("/api/ml/train/").json()
    assert run["status"] == "trained" and run["feature_version"] == 2

    default = client.get("/api/ml/economics/")
    assert default.status_code == 200 and default.json() == run["economics"]
    custom = client.get("/api/ml/economics/?margin_pct=50&keep_rate=0.2").json()
    assert custom["assumptions"] == {**run["economics"]["assumptions"], "margin_pct": 50.0, "keep_rate": 0.2}
    assert custom["table"][0]["margin_lost_inr"] != run["economics"]["table"][0]["margin_lost_inr"]


# ---------------------------------------------------------------- M5 step 3: the scoring engine
ASHA = "9876543210"     # the fixture customer: A1 ordered 1 Mar (delivered 4 Mar), A2 ordered 2 Mar (came back;
                        # no return date in the file, so its outcome counts as known 10 days after the 3 Mar pickup)


def shipped(client):  # noqa: F811
    run(client, "orders", ORDERS)
    run(client, "shipments", SHIPMENTS)
    return client.merchant


def live(ts, **extra):
    return {"order_value": 500, "payment_mode": "COD", "pincode": "411001", "phone": ASHA, "order_ts": ts, **extra}


def test_live_history_only_counts_what_was_known_before_each_order(client):  # noqa: F811
    from ml.score import build_features
    m = shipped(client)
    f = build_features(m, [
        live("2025-03-01T09:00:00+05:30"),                  # before A1 was placed
        live("2025-03-02T18:30:00+05:30", order_id="A2"),   # A2 itself, re-scored: must not count itself
        live("2025-03-05T12:00:00+05:30"),                  # A1 delivered, A2's outcome not yet known
        live("2025-03-20T12:00:00+05:30"),                  # both outcomes known
    ])

    assert f.prior_orders.tolist() == [0, 1, 2, 2]
    assert f.cust_prior_delivered.tolist() == [0, 0, 1, 1]
    assert f.cust_prior_rto.tolist() == [0, 0, 0, 1]
    assert f.pin_prior_parcels.tolist() == [0, 0, 1, 2]
    assert f.base_rto_rate.tolist() == [0.2, 0.2, 0.0, 0.5]   # merchant-wide, also only what was known then


def test_live_features_match_the_training_rows(client):  # noqa: F811
    from core.models import Customer
    from ledger.models import ShipmentLedger
    from ml.features import training_frame
    from ml.score import build_features
    m = shipped(client)
    tf = training_frame(m)
    ref = dict(ShipmentLedger.objects.filter(merchant=m).values_list("shipment_id", "order_ref"))
    cust = {c.id: c for c in Customer.objects.filter(merchant=m)}
    orders = [{"order_id": ref[r.shipment_id], "customer_id": cust[r.customer_id].external_id, "pincode": r.pincode,
               "address": cust[r.customer_id].address_line, "payment_mode": "COD" if r.is_cod else "Prepaid",
               "order_value": r.order_value, "sales_channel": r.sales_channel, "order_ts": r.order_ts}
              for r in tf.itertuples()]

    f = build_features(m, orders)

    cols = NUMERIC + ["prior_orders", "cust_prior_rto", "cust_prior_delivered", "pin_prior_parcels", "base_rto_rate"]
    assert len(tf) == 2
    assert np.allclose(f[cols].astype(float).to_numpy(), tf[cols].astype(float).to_numpy())


def test_stale_model_is_never_scored_and_a_current_one_is(client, monkeypatch):  # noqa: F811
    from ml import score, train
    from ml.train import RISK_BANDS
    m = shipped(client)
    m4_model(m)                                                            # active, but old features
    monkeypatch.setattr(score, "load_artifact", lambda run: pytest.fail("a stale artifact was loaded"))
    assert score.scorer_for(m) == (None, RISK_BANDS)
    [r] = score.score_orders(m, [live("2025-04-01T14:00:00+05:30")])
    assert r["scored_by"] == "rules"

    monkeypatch.undo()
    monkeypatch.setattr(train, "training_frame", lambda merchant: synthetic())
    first = client.post("/api/ml/train/").json()
    scorer, bands = score.scorer_for(m)
    assert scorer is not None and bands == RISK_BANDS and list(score._cache) == [first["id"]]
    [r] = score.score_orders(m, [live("2025-04-01T14:00:00+05:30", address="Flat 2, FC Road, Pune")])
    assert r["scored_by"] == f"model:{first['chosen']}" and 0 < r["risk_probability"] < 1
    assert r["risk_category"] in score.BAND_NAMES and r["risk_pct"] == round(100 * r["risk_probability"], 1)
    for factor in r["contributing_factors"]:
        assert set(factor) == {"factor", "value", "effect", "strength"} and factor["strength"] >= score.MIN_STRENGTH

    second = client.post("/api/ml/train/").json()                          # a new model replaces the cached one
    score.scorer_for(m)
    assert list(score._cache) == [second["id"]]


def test_inputs_are_normalised_and_the_phone_never_comes_back(client):  # noqa: F811
    import json

    from ml.score import build_features, score_orders
    m = shipped(client)
    f = build_features(m, [live("2025-03-20T12:00:00+05:30", phone="+91 98765 43210", pincode=" 411 001",
                                sales_channel="  website ", payment_mode="Cash on Delivery"),
                           live("2025-03-20T12:00:00+05:30", phone="1234567890")])   # not a mobile number
    assert f.customer_pk.notna().tolist() == [True, False]
    assert f.pincode.tolist() == ["411001", "411001"] and f.sales_channel[0] == "Website" and f.is_cod[0] == 1

    results = score_orders(m, [live("2025-03-20T12:00:00+05:30")])
    assert ASHA not in json.dumps(results) and "phone" not in json.dumps(results)
    assert results[0]["customer"] == {"known": True, "previous_orders": 2, "delivered": 1, "returned": 1}
