"""Clean every column, reject rows that can't be trusted, and report exactly why."""
import hashlib

import pandas as pd
from django.conf import settings
from django.utils import timezone

from core.models import Order, Shipment

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


def _zone(s):
    z = s.str.upper().str.replace(r"ZONE|[\s\-_]", "", regex=True)
    return z.where(z.str.fullmatch(r"[A-Z0-9]{1,2}"))


def _bool(s):
    yes, no = {"yes", "y", "true", "1", "available"}, {"no", "n", "false", "0", "not available"}
    low = s.str.lower()
    return low.map(lambda v: True if v in yes else False if v in no else None, na_action="ignore")


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
    "zone": lambda s, f: _zone(s),
    "bool": lambda s, f: _bool(s),
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


def grams(df, col, rep):
    """Nobody ships 0.4 gram parcels. If the typical value is tiny, the file is in kg."""
    if df[col].median() < 50:
        df[col] = df[col] * 1000
        rep.warn(df[col].notna(), "weight_looked_like_kg_converted_to_g", col)


def warn_unknown_awb(df, rep, merchant):
    known = set(Shipment.objects.for_merchant(merchant).values_list("awb_number", flat=True))
    rep.warn(df.awb_number.notna() & ~df.awb_number.isin(known), "awb_not_in_shipments", "awb_number")


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
    grams(df, "pkg_weight_g", rep)
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


def pincode_zones_rules(df, rep, merchant):
    rep.reject(df.pincode.duplicated(keep="first") & df.pincode.notna(), "duplicate_in_file", "pincode")
    df["city_tier"] = df.city_tier.fillna(1)
    df["cod_serviceable"] = df.cod_serviceable.map(lambda v: True if v is None or pd.isna(v) else bool(v))


def rate_card_rules(df, rep, merchant):
    both = df.courier.notna() & df.zone.notna()
    rep.reject(df.duplicated(["courier", "zone"], keep="first") & both, "duplicate_in_file", "zone")
    rep.reject(df.first_500g_inr <= 0, "rate_not_positive", "first_500g_inr")
    rep.reject(df.addl_500g_inr <= 0, "rate_not_positive", "addl_500g_inr")
    df["cod_fee_pct"] = df.cod_fee_pct.fillna(0)
    df["cod_min_inr"] = df.cod_min_inr.fillna(0)
    df["rto_charge_pct_of_freight"] = df.rto_charge_pct_of_freight.fillna(100)


def invoices_rules(df, rep, merchant):
    """A repeated AWB or an unknown AWB is NOT rejected here. Those are billing errors, and the
    audit engine can only catch them if they are stored. We reject only what we cannot read."""
    for c in ["cod_charge_inr", "rto_freight_inr", "gst_inr"]:
        df[c] = df[c].fillna(0)

    rep.reject(df.billed_weight_g <= 0, "weight_not_positive", "billed_weight_g")
    grams(df, "billed_weight_g", rep)

    money = ["forward_freight_inr", "cod_charge_inr", "rto_freight_inr", "gst_inr", "total_billed_inr"]
    rep.reject((df[money] < 0).any(axis=1), "negative_amount", "total_billed_inr")

    parts = df.forward_freight_inr + df.cod_charge_inr + df.rto_freight_inr + df.gst_inr
    rep.warn((parts - df.total_billed_inr).abs() > 1, "total_does_not_match_components", "total_billed_inr")

    warn_unknown_awb(df, rep, merchant)

    # no line id in the file? build a stable one, so re-uploading the same invoice updates it
    nth = (df.groupby(["invoice_id", "awb_number"]).cumcount() + 1).astype(str)
    df["line_ref"] = df.line_ref.fillna(df.invoice_id + "|" + df.awb_number + "|" + nth)

    rep.reject(df.line_ref.duplicated(keep="first") & df.line_ref.notna(), "duplicate_in_file", "line_ref")


def remittances_rules(df, rep, merchant):
    df["utr_batch"] = df.utr_batch.fillna("")

    rep.reject(df.amount_remitted_inr <= 0, "amount_not_positive", "amount_remitted_inr")

    rep.reject(
        df.duplicated(["awb_number", "remittance_date", "utr_batch"], keep="first") & df.awb_number.notna(),
        "duplicate_in_file",
        "awb_number"
    )

    warn_unknown_awb(df, rep, merchant)


RULES = {
    "orders": orders_rules,
    "shipments": shipments_rules,
    "pincode_zones": pincode_zones_rules,
    "rate_card": rate_card_rules,
    "invoices": invoices_rules,
    "remittances": remittances_rules,
}


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
