import io

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import CATEGORICAL, IST, LABELS, NUMERIC, TARGET, design_matrix, training_frame
from .models import RiskModel

MIN_ROWS = 2000
MIN_RTO = 200
TRAIN_SHARE = 0.70
VALID_SHARE = 0.15
LGB_MARGIN = 0.005
MARGIN_PCT = 30.0
KEEP_RATE = 0.6
RISK_BANDS = {
    "medium_from": 0.10,
    "high_from": 0.25,
    "very_high_from": 0.50,
}
FEATURE_VERSION = 2         # M4 models had no version (old 26-column features); M5 features are version 2

LGB_PARAMS = {
    "objective": "binary",
    "metric": "auc",
    "learning_rate": 0.03,
    "num_leaves": 7,
    "min_data_in_leaf": 60,
    "lambda_l2": 5,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "seed": 42,
    "deterministic": True,
    "num_threads": 1,
    "verbose": -1,
}
LGB_MAX_ROUNDS = 2000
LGB_EARLY_STOP = 100
THRESHOLDS = np.round(np.arange(0.10, 0.80 + 1e-9, 0.05), 2)
BANDS = [(0.00, 0.05, "0-5%"), (0.05, 0.10, "5-10%"), (0.10, 0.20, "10-20%"),
         (0.20, 0.35, "20-35%"), (0.35, 0.50, "35-50%"), (0.50, 1.01, "50%+")]
TOP_FEATURES = 10
EPS = 1e-6


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def base_feature(column):
    """'zone=A' -> 'zone'; numeric columns are their own base."""
    return column.split("=", 1)[0]


def label_for(column):
    base = base_feature(column)
    label = LABELS.get(base, base)
    return f"{label}: {column.split('=', 1)[1]}" if "=" in column else label


class Scorer:
    """The chosen model, its calibrator and the training columns. Pickled into the RiskModel artifact."""

    def __init__(self, kind, model, columns):
        self.kind = kind            # "logistic" (sklearn pipeline) or "lightgbm" (lgb.Booster)
        self.model = model
        self.columns = list(columns)
        self.calibrator = None

    def matrix(self, d):
        return design_matrix(d, columns=self.columns)

    def raw(self, X):
        if self.kind == "lightgbm":
            return self.model.predict(X, num_iteration=self.model.best_iteration)
        return self.model.predict_proba(X)[:, 1]

    def calibrate(self, X_valid, y_valid):
        self.calibrator = LogisticRegression().fit(_logit(self.raw(X_valid)).reshape(-1, 1), y_valid)
        return self

    def predict_proba(self, X):
        """Calibrated probability of RTO for each row of a design matrix."""
        raw = self.raw(X)
        if self.calibrator is None:
            return raw
        return self.calibrator.predict_proba(_logit(raw).reshape(-1, 1))[:, 1]

    def score(self, d):
        """Calibrated probability of RTO for each row of a feature frame."""
        return self.predict_proba(self.matrix(d))

    def contributions(self, X):
        """Per-row push of each column on the model's log-odds (before calibration)."""
        if self.kind == "lightgbm":
            contrib = self.model.predict(X, num_iteration=self.model.best_iteration, pred_contrib=True)[:, :-1]
        else:
            scaler, logreg = self.model.named_steps["standardscaler"], self.model.named_steps["logisticregression"]
            contrib = scaler.transform(X) * logreg.coef_[0]
        return pd.DataFrame(contrib, columns=self.columns, index=getattr(X, "index", None))

    def importance(self):
        """Share of the model's total importance per feature (one-hot columns folded into their feature)."""
        if self.kind == "lightgbm":
            raw = self.model.feature_importance(importance_type="gain", iteration=self.model.best_iteration)
        else:
            raw = np.abs(self.model.named_steps["logisticregression"].coef_[0])
        s = pd.Series(raw, index=self.columns, dtype=float).groupby(base_feature).sum()
        s = s / s.sum() if s.sum() > 0 else s
        return [{"feature": f, "label": LABELS.get(f, f), "share_pct": round(float(100 * v), 1)}
                for f, v in s.sort_values(ascending=False).items()]

    def labels(self):
        return {c: label_for(c) for c in self.columns}


def chronological_split(d):
    n = len(d)
    a, b = int(n * TRAIN_SHARE), int(n * (TRAIN_SHARE + VALID_SHARE))
    return d.iloc[:a], d.iloc[a:b], d.iloc[b:]


def _period(part):
    local = part["order_ts"].dt.tz_convert(IST)
    return {"rows": len(part), "from": local.min().date().isoformat(), "to": local.max().date().isoformat(),
            "rto_rate_pct": round(float(100 * part[TARGET].mean()), 1)}


def scores(y, p):
    return {
        "auc": round(float(roc_auc_score(y, p)), 3),
        "avg_precision": round(float(average_precision_score(y, p)), 3),
        "brier": round(float(brier_score_loss(y, p)), 4),
    }


def bands(y, p):
    """Calibration check: in each score band, how often did those orders actually come back?"""
    y, p = np.asarray(y), np.asarray(p)
    out = []
    for lo, hi, name in BANDS:
        m = (p >= lo) & (p < hi)
        if m.any():                     # empty bands are left out
            out.append({"score_band": name, "orders": int(m.sum()),
                        "avg_predicted": round(float(p[m].mean()), 4),
                        "actual_rto_rate": round(float(y[m].mean()), 4)})
    return out


def top_share(y, p, share=0.10):
    """Percent of all RTOs that sit in the riskiest `share` of orders."""
    y, p = np.asarray(y), np.asarray(p)
    top = np.argsort(-p, kind="stable")[: max(1, int(np.ceil(len(p) * share)))]
    return round(float(100 * y[top].sum() / y.sum()), 1) if y.sum() else 0.0


def rto_cost(train):
    """Average courier bill on returned parcels in the training rows (forward + RTO freight)."""
    billed = train.loc[(train[TARGET] == 1) & (train["billed_total_inr"] > 0), "billed_total_inr"]
    return round(float(billed.mean()), 2) if len(billed) else 0.0


def economics(test, p, cost, margin_pct=MARGIN_PCT, keep_rate=KEEP_RATE):
    """For COD orders only: flagging an order that would have come back saves its RTO cost; flagging a good
    order loses its margin on the share of those customers who walk away (1 - keep_rate)."""
    cod = test["is_cod"].to_numpy() == 1
    y = test[TARGET].to_numpy()[cod]
    value = test["order_value"].to_numpy(dtype=float)[cod]
    p = np.asarray(p)[cod]
    table = []
    for t in THRESHOLDS:
        flag = p >= t
        caught, good = flag & (y == 1), flag & (y == 0)
        saved = caught.sum() * cost
        lost = (value[good] * margin_pct / 100 * (1 - keep_rate)).sum()
        table.append({"threshold": float(t), "orders_flagged": int(flag.sum()), "rto_caught": int(caught.sum()),
                      "good_orders_flagged": int(good.sum()), "saved_inr": int(round(float(saved))),
                      "margin_lost_inr": int(round(float(lost))), "net_inr": int(round(float(saved - lost)))})
    best = max((r for r in table if r["net_inr"] > 0), key=lambda r: r["net_inr"], default=None)
    return {
        "assumptions": {"rto_cost_inr": cost, "margin_pct": margin_pct, "keep_rate": keep_rate},
        "cod_orders_in_test": int(cod.sum()),
        "cod_rto_in_test": int(y.sum()),
        "cod_rto_cost_in_test_inr": round(float(y.sum() * cost)),
        "table": table,
        "best": best,
    }


def fit(d):
    """Fit both models on the oldest rows, pick and calibrate on validation, report on test.
    Returns (scorer, metrics, test rows). Raises ValueError if a period lacks both outcomes."""
    train, valid, test = chronological_split(d)
    for name, part in (("train", train), ("validation", valid), ("test", test)):
        if part[TARGET].nunique() < 2:
            raise ValueError(f"The {name} period has only one outcome, so the model cannot be evaluated.")

    X_train = design_matrix(train)
    columns = list(X_train.columns)
    X_valid, X_test = design_matrix(valid, columns), design_matrix(test, columns)
    y_train, y_valid, y_test = train[TARGET].to_numpy(), valid[TARGET].to_numpy(), test[TARGET].to_numpy()

    logistic = Scorer("logistic", make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)), columns)
    logistic.model.fit(X_train, y_train)
    booster = lgb.train(
        LGB_PARAMS,
        lgb.Dataset(X_train, y_train),
        LGB_MAX_ROUNDS,
        valid_sets=[lgb.Dataset(X_valid, y_valid)],
        callbacks=[lgb.early_stopping(LGB_EARLY_STOP, verbose=False)],
    )
    lightgbm = Scorer("lightgbm", booster, columns)

    candidates = {s.kind: {"valid": scores(y_valid, s.raw(X_valid)), "test": scores(y_test, s.raw(X_test))}
                  for s in (logistic, lightgbm)}
    use_lgb = candidates["lightgbm"]["valid"]["auc"] >= candidates["logistic"]["valid"]["auc"] + LGB_MARGIN
    chosen = (lightgbm if use_lgb else logistic).calibrate(X_valid, y_valid)

    p_test = chosen.predict_proba(X_test)
    money = economics(test, p_test, rto_cost(train))
    metrics = {
        "rows": len(d),
        "rto": int(d[TARGET].sum()),
        "chosen": chosen.kind,
        "lgb_best_iteration": int(booster.best_iteration),
        "split": {"train": _period(train), "valid": _period(valid), "test": _period(test)},
        "candidates": candidates,
        "test_after_calibration": scores(y_test, p_test),
        "brier_if_we_predicted_the_average": round(float(brier_score_loss(y_test, np.full(len(y_test),
                                                                                         y_test.mean()))), 4),
        "top_10pct_of_orders_hold_pct_of_rto": top_share(y_test, p_test),
        "top_features": chosen.importance()[:TOP_FEATURES],
        "economics": money,
        "bands": bands(y_test, p_test),                 # six-bin calibration check, unchanged from M4
        "risk_bands": dict(RISK_BANDS),                 # fixed cut-offs for Low / Medium / High / Very high
        "cod_prepaid_threshold": money["best"]["threshold"] if money["best"] else None,
        "feature_columns": list(chosen.columns),
        "feature_version": FEATURE_VERSION,
    }
    return chosen, metrics, test


def _insufficient(merchant, metrics):
    return RiskModel.objects.create(merchant=merchant, status=RiskModel.Status.INSUFFICIENT_DATA,
                                    is_active=False, metrics=metrics)


def train_model(merchant):
    """Train this merchant's model. On success the new model becomes the active one; on too little data
    an inactive record explains why, and the current active model is left alone."""
    d = training_frame(merchant)
    rows, rto = len(d), int(d[TARGET].sum()) if len(d) else 0
    counts = {"rows": rows, "rto": rto, "rto_rate": round(rto / rows, 4) if rows else None,
              "min_rows": MIN_ROWS, "min_rto": MIN_RTO}
    if rows < MIN_ROWS or rto < MIN_RTO:
        return _insufficient(merchant, {**counts, "reason": f"Need at least {MIN_ROWS} shipments with a known "
                                                            f"outcome and {MIN_RTO} RTOs."})
    try:
        scorer, metrics, test = fit(d)
    except ValueError as e:
        return _insufficient(merchant, {**counts, "reason": str(e)})

    buf = io.BytesIO()
    joblib.dump({"scorer": scorer, "test": test,
                 "rto_cost": metrics["economics"]["assumptions"]["rto_cost_inr"]}, buf)
    name = f"rto_m{merchant.pk}_{timezone.now():%Y%m%d%H%M%S}.joblib"

    model = RiskModel(merchant=merchant, status=RiskModel.Status.TRAINED, is_active=False, metrics=metrics)
    model.artifact.save(name, ContentFile(buf.getvalue()), save=False)
    try:
        with transaction.atomic():
            model.save()
            RiskModel.objects.for_merchant(merchant).filter(is_active=True).exclude(pk=model.pk).update(is_active=False)
            model.is_active = True
            model.save(update_fields=["is_active"])
    except Exception:
        model.artifact.delete(save=False)     # the database rolled back; do not leave an orphan file
        raise
    return model


def active_model(merchant):
    """This merchant's active trained model, or None."""
    return (RiskModel.objects.for_merchant(merchant)
            .filter(is_active=True, status=RiskModel.Status.TRAINED).first())


def current_feature_columns(run):
    """The columns a model trained on today's features would have: every NUMERIC feature, in order, then
    one-hot columns of today's CATEGORICAL features. Which zones and channels appear depends on the
    merchant's data, so the model's own one-hot values are kept; only their feature names are checked."""
    saved = run.metrics.get("feature_columns") or []
    onehot = [c for c in saved if "=" in c and base_feature(c) in CATEGORICAL]
    return [*NUMERIC, *onehot]


def model_feature_compatible(run):
    """True only for a trained model built on the current feature set. M4 models (no version) are stale."""
    return (
        run.status == RiskModel.Status.TRAINED
        and run.metrics.get("feature_version") == FEATURE_VERSION
        and run.metrics.get("feature_columns") == current_feature_columns(run)
    )


def load_artifact(run):
    """{"scorer", "test", "rto_cost"} saved by train_model() for a trained RiskModel."""
    with run.artifact.open("rb") as f:
        return joblib.load(f)
