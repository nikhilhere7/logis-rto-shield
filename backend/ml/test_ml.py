import numpy as np
import pandas as pd

from ingestion.test_ingestion import ORDERS, SHIPMENTS, client, run  # noqa: F401
from ml.features import CATEGORICAL, NUMERIC, address_features, design_matrix, time_aware_history
from ml.models import RiskModel
from ml.train import TRAIN_SHARE, VALID_SHARE, economics, fit

UTC = lambda s: pd.Timestamp(s, tz="UTC")   # noqa: E731


def synthetic(n=3000, seed=0):
    """Fake order history in time order: COD orders with short addresses come back more often."""
    r = np.random.default_rng(seed)
    d = pd.DataFrame({c: r.random(n) for c in NUMERIC})
    d["is_cod"] = (r.random(n) < 0.5).astype(int)
    d["order_value"] = r.uniform(300, 3000, n)
    d["zone"] = r.choice(list("ABCDE"), n)
    d["sales_channel"] = r.choice(["Website", "WhatsApp"], n)
    d["is_rto"] = (r.random(n) < 0.08 + 0.4 * d["is_cod"] * (1 - d["addr_len"])).astype(int)
    d["order_ts"] = pd.date_range("2024-01-01", periods=n, freq="3h", tz="UTC")
    d["billed_total_inr"] = r.uniform(60, 200, n)
    return d


def test_no_future_or_leaky_features():
    features = NUMERIC + CATEGORICAL
    leaky = ["courier", "deliver", "final_status", "pickup", "billed", "remit", "invoice", "ndr", "attempt",
             "is_rto", "is_lost", "on_time", "days_", "weight", "cod_due"]
    assert not [f for f in features if any(word in f for word in leaky) and f != "cust_prior_delivered"]
    # cust_prior_delivered is a count of *earlier* deliveries, which test 2 proves are known in time
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
    assert 0 < h.pin_prior_rto_rate[12] < 1


def test_address_features():
    a = address_features(pd.Series(["flat 2, fc road, near temple", "Ganesh Society, FC Road, Opp. SBI ATM",
                                     None, ""], index=[7, 8, 9, 10]))

    assert list(a.columns) == ["addr_len", "addr_words", "addr_commas", "addr_has_number",
                               "addr_has_landmark", "addr_is_lowercase"]
    assert list(a.index) == [7, 8, 9, 10]
    assert a.loc[7].tolist() == [28, 6, 2, 1, 1, 1]
    assert a.loc[8].tolist() == [37, 7, 2, 0, 1, 0]       # "Opp." counts as a landmark, any case
    assert a.loc[9].tolist() == a.loc[10].tolist() == [0, 0, 0, 0, 0, 0]


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
