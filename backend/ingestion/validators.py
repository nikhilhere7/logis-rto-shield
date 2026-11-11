"""Clean every column, reject rows that can't be trusted, and report exactly why."""
import hashlib

import pandas as pd
from django.conf import settings
from django.utils import timezone

from core.models import Order

from .schemas import SPECS

BLANKS = {"", "nan", "none", "null", "na", "n/a", "-"}


class MappingError(Exception):
    pass


class Report:
    def __init__(self, index):
        self.bad = pd.Series(False, index=index)
        self.errors, self.warnings = [], []

    @staticmethod
    def _entry(mask, rule, field):
        rows = [int(i) + 2 for i in mask[mask].index[:5]]
        return {"rule": rule, "field": field, "count": int(mask.sum()), "sample_rows": rows}

    def reject(self, mask, rule, field):
        mask = mask.fillna(False).astype(bool)
        if mask.any():
            self.errors.append(self._entry(mask, rule, field))
            self.bad |= mask

    def warn(self, mask, rule, field):
        mask = mask.fillna(False).astype(bool)
        if mask.any():
            self.warnings.append(self._entry(mask, rule, field))

    def as_dict(self):
        n = len(self.bad)
        return {
            "total_rows": n,
            "valid_rows": int(n - self.bad.sum()),
            "rejected_rows": int(self.bad.sum()),
            "errors": self.errors,
            "warnings": self.warnings,
        }


def _number(s):
    s = s.str.replace(r"(?i)rs\.?|inr|₹|,|\s", "", regex=True)
    return pd.to_numeric(s, errors="coerce")


TZ_SUFFIX = r"(?i)\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?\s*(?:z|[+-]\d{2}:?\d{2})$"


def _parse_ts(s, utc):
    out = pd.to_datetime(s, format="ISO8601", errors="coerce", utc=utc)
    rest = out.isna() & s.notna()
    if rest.any():
        out[rest] = pd.to_datetime(
            s[rest], format="mixed", dayfirst=True, errors="coerce", utc=utc
        )
    return out


def _ts(s):
    """Naive values are read as local time (settings.TIME_ZONE, Asia/Kolkata);
    values with an offset or Z are converted to local time. Returns naive local datetimes."""
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    aware = s.str.contains(TZ_SUFFIX, regex=True, na=False)
    if (~aware).any():
        out[~aware] = _parse_ts(s[~aware], utc=False)
    if aware.any():
        out[aware] = (
            _parse_ts(s[aware], utc=True)
            .dt.tz_convert(settings.TIME_ZONE)
            .dt.tz_localize(None)
        )
    return out


def _pincode(s):
    s = s.str.replace(r"\.0$", "", regex=True).str.replace(r"\s", "", regex=True)
    return s.where(s.str.fullmatch(r"[1-9]\d{5}"))


def _phone(s):
    digits = s.str.replace(r"\D", "", regex=True).str[-10:]
    return digits.where(digits.str.fullmatch(r"[6-9]\d{9}"))


def _choice(s, f):
    lookup = {
        raw: canon
        for canon, raws in f.choices.items()
        for raw in raws + (canon.lower(),)
    }
    return s.str.lower().map(lookup)


CLEANERS = {
    "id": lambda s, f: s.str.replace(r"\.0$", "", regex=True),
    "str": lambda s, f: s,
    "ts": lambda s, f: _ts(s),
    "date": lambda s, f: _ts(s).dt.normalize(),
    "money": lambda s, f: _number(s),
    "num": lambda s, f: _number(s),
    "int": lambda s, f: _number(s).round(),
    "pincode": lambda s, f: _pincode(s),
    "phone": lambda s, f: _phone(s),
    "choice": _choice,
}


def hash_phone(phone):
    return hashlib.sha256((settings.PHONE_HASH_SALT + phone).encode()).hexdigest()


def orders_rules(df, rep, merchant):
    rep.reject(
        df.order_id.duplicated(keep="first") & df.order_id.notna(),
        "duplicate_in_file", "order_id"
    )
    now = timezone.localtime().replace(tzinfo=None)
    rep.reject(df.order_ts > now, "date_in_future", "order_ts")
    rep.reject(df.order_value < 0, "negative_amount", "order_value")
    rep.reject(
        df.customer_id.isna() & df.customer_phone.isna(),
        "no_customer_id_or_phone", "customer_id"
    )
    rep.warn(df.address_line.isna(), "missing_address", "address_line")
    df["status"] = df.status.fillna("Shipped")
    df["gross_value"] = df.gross_value.fillna(df.order_value)
    df["discount_inr"] = df.discount_inr.fillna(0)
    df["shipping_fee_inr"] = df.shipping_fee_inr.fillna(0)
    df["phone_hash"] = df.customer_phone.map(hash_phone, na_action="ignore")
    df["customer_key"] = df.customer_id.fillna("PH-" + df.phone_hash.str[:16])
    df.drop(columns=["customer_phone"], inplace=True)


def shipments_rules(df, rep, merchant):
    rep.reject(
        df.awb_number.duplicated(keep="first") & df.awb_number.notna(),
        "duplicate_in_file", "awb_number"
    )
    known = set(
        Order.objects.for_merchant(merchant).values_list("external_id", flat=True)
    )
    rep.reject(
        df.order_id.notna() & ~df.order_id.isin(known),
        "order_not_found", "order_id"
    )
    rep.reject(df.pkg_weight_g <= 0, "weight_not_positive", "pkg_weight_g")
    if df.pkg_weight_g.median() < 50:
        df["pkg_weight_g"] = df.pkg_weight_g * 1000
        rep.warn(
            df.pkg_weight_g.notna(),
            "weight_looked_like_kg_converted_to_g", "pkg_weight_g"
        )
    rep.warn(
        (df.final_status == "Delivered") & df.delivered_ts.isna(),
        "delivered_without_date", "delivered_ts"
    )
    rep.warn(
        df.pkg_length_cm.isna() | df.pkg_breadth_cm.isna() | df.pkg_height_cm.isna(),
        "missing_dimensions_volumetric_check_skipped", "pkg_length_cm"
    )
    for c in ["pkg_length_cm", "pkg_breadth_cm", "pkg_height_cm", "delivery_attempts"]:
        df[c] = df[c].fillna(0)


RULES = {"orders": orders_rules, "shipments": shipments_rules}


def read_file(path):
    path = str(path)
    if path.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(path, dtype=str, keep_default_na=False)
    return pd.read_csv(
        path, dtype=str, keep_default_na=False, encoding_errors="replace"
    )


def run_validation(raw, dataset_type, mapping, merchant):
    """raw: DataFrame of strings. Returns (clean rows only, report dict)."""
    spec = SPECS[dataset_type]
    missing = [
        f for f in spec.required
        if not mapping.get(f) or mapping[f] not in raw.columns
    ]
    if missing:
        raise MappingError(
            f"Required fields not mapped to a column: {', '.join(missing)}"
        )

    rep = Report(raw.index)
    df = pd.DataFrame(index=raw.index)

    for f in spec.fields:
        src = mapping.get(f.name)
        if not src or src not in raw.columns:
            df[f.name] = None
            continue

        text = raw[src].astype("object").map(lambda v: str(v).strip())
        blank = text.str.lower().isin(BLANKS)
        text = text.mask(blank)
        clean = CLEANERS[f.kind](text, f)
        unreadable = clean.isna() & ~blank

        if f.required:
            rep.reject(blank, "missing_required_value", f.name)
            rep.reject(unreadable, f"invalid_{f.kind}", f.name)
        else:
            rep.warn(unreadable, f"invalid_{f.kind}_left_blank", f.name)

        df[f.name] = clean

    RULES[dataset_type](df, rep, merchant)
    return df[~rep.bad].copy(), rep.as_dict()
