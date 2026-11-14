"""The five reports. Each one reads the same functions the dashboard's API uses, so a PDF can never
disagree with the screen. Nothing here writes to the database or to disk.

Every report has three parts (see pdf.render): an introduction, the report, and a conclusion.
The conclusion's findings and next steps are worked out from the merchant's own numbers. A sentence is only
written when the data supports it, so a report on thin data has a short conclusion, never an invented one."""
from datetime import date

from audit.reports import findings as audit_findings, summary as audit_summary
from core.models import CodRemittance, InvoiceLine, Order, PincodeZone, RateCard, Shipment
from customers.profiles import customer_table, segment_summary
from ledger import metrics
from ledger.models import ShipmentLedger

from . import charts
from .pdf import callout, chart, count, esc, gap, h3, inr, para, pct, render, room, section, table, tiles, together

GAP_POINTS = 5  # two return rates must differ by this many points before the report calls one worse


def month_name(ym):
    """'2025-12' -> 'Dec 2025'."""
    try:
        y, m = (int(x) for x in str(ym).split("-")[:2])
        return date(y, m, 1).strftime("%b %Y")
    except (ValueError, TypeError):
        return str(ym)


def period(merchant):
    months = [m for m in metrics.monthly(merchant) if m["shipments"]]
    if not months:
        return "No shipments yet", months
    first, last = month_name(months[0]["month"]), month_name(months[-1]["month"])
    return (first if first == last else f"{first} to {last}"), months


def trend(months):
    labels = [date(*(int(x) for x in m["month"].split("-")[:2]), 1).strftime("%b %y") for m in months]
    return chart(charts.line(labels, [m["rto_rate_pct"] or 0 for m in months]))


def name(v, blank="Not recorded"):
    return str(v) if v not in (None, "") else blank


def noun(v, word, many=None):
    """1 charge, 2 charges: the word that goes with a count."""
    return word if v == 1 else (many or word + "s")


def b(text):
    """Bold a value inside a sentence. The value is escaped, because it may be a merchant's own text."""
    return f"<b>{esc(text)}</b>"


def sources(merchant):
    """The uploaded data a report draws on, as (file, rows). Shown on the introduction page."""
    rows = [("Orders", Order), ("Shipments", Shipment), ("Courier invoice lines", InvoiceLine), ("COD remittance lines", CodRemittance),
            ("Rate card rows", RateCard), ("Pincode zones", PincodeZone)]
    return [(label, model.objects.for_merchant(merchant).count()) for label, model in rows]


def worst(rows, key, floor=0):
    """The row with the highest value of `key`, and the runner-up, among rows with enough parcels."""
    ranked = sorted((r for r in rows if r.get(key) is not None and r.get("shipments", floor) >= floor), key=lambda r: r[key], reverse=True)
    return (ranked[0], ranked[-1]) if len(ranked) > 1 else (None, None)


LIMITS = ["It only knows what is in the uploaded files. Parcels, bills or payments missing from those files are missing here.",
          "It covers everything uploaded so far, not a chosen date range.",
          "A parcel still on its way has no outcome yet, so it is not counted as delivered or returned."]


# ---------------------------------------------------------------- 1. business summary
def business_summary(merchant):
    o = metrics.overview(merchant)
    span, months = period(merchant)
    a = audit_summary(merchant)
    by_mode = {r["payment_mode"]: r for r in metrics.rto_by(merchant, "payment_mode")}
    couriers = metrics.rto_by(merchant, "courier")
    cod, prepaid = by_mode.get("COD"), by_mode.get("Prepaid")

    story = [*section("Overview", "The business at a glance"),
             tiles([("Orders", count(o["total_orders"]), f"{count(o['cancelled_orders'])} cancelled"),
                    ("Delivered revenue", inr(o["delivered_revenue_inr"]), f"{pct(o['delivered_rate_pct'])} of parcels delivered"),
                    ("Return rate", pct(o["rto_rate_pct"]), f"{count(o['rto'])} of {count(o['total_shipments'])} {noun(o['total_shipments'], 'parcel')}"),
                    ("Recoverable from couriers", inr(a["total_recoverable_inr"]), f"{count(a['findings'])} {noun(a['findings'], 'charge')} to dispute")]),
             gap(),
             tiles([("Courier charges on returns", inr(o["rto_courier_cost_inr"]), "paid for parcels that came back"),
                    ("Value of returned orders", inr(o["rto_order_value_inr"]), "shipped and not kept"),
                    ("Delivered on time", pct(o["on_time_pct"]), f"{o['avg_delivery_days'] if o['avg_delivery_days'] is not None else '-'} days on average"),
                    ("Billed by couriers", inr(o["total_courier_billed_inr"]), f"{pct(a['overcharge_pct_of_billed'])} of it was overcharged")])]
    if len(months) > 1:
        story.append(together(section("Returns", "Return rate, month by month"), trend(months)))
    if cod and prepaid:
        story.append(together(section("Payment", "Cash on delivery against prepaid"),
                              table(["Payment", "Parcels", "Returned", "Return rate", "Courier charges on returns"],
                                    [[label, count(r["shipments"]), count(r["rto"]), pct(r["rto_rate_pct"]), inr(r["rto_courier_cost_inr"])]
                                     for label, r in (("Cash on delivery", cod), ("Prepaid", prepaid))], [0.3, 0.15, 0.15, 0.15, 0.25], right=(1, 2, 3, 4))))
    if a["by_kind"]:
        kinds = a["by_kind"]
        story.append(together(section("Courier claims", "Where the claim against couriers comes from"),
                              chart(charts.bars([k["label"] for k in kinds], [k["claim_inr"] for k in kinds], fmt=charts.rupees, colour=charts.TEAL))))
    if couriers:
        speed = {d["courier"]: d for d in metrics.delivery_by(merchant, "courier")}
        story.append(together(section("Couriers", "Couriers at a glance"),
                              table(["Courier", "Parcels", "Return rate", "On time", "Days to deliver"],
                                    [[name(c["courier"], "Unknown courier"), count(c["shipments"]), pct(c["rto_rate_pct"]), pct(speed.get(c["courier"], {}).get("on_time_pct")),
                                      name(speed.get(c["courier"], {}).get("avg_delivery_days"), "-")] for c in couriers], [0.36, 0.16, 0.16, 0.16, 0.16], right=(1, 2, 3, 4))))

    found, act = [], []
    if o["rto"]:
        found.append(f"{b(pct(o['rto_rate_pct']))} of parcels came back. That is {b(count(o['rto']))} {noun(o['rto'], 'parcel')}, and the couriers charged {b(inr(o['rto_courier_cost_inr']))} to carry them both ways.")
    if cod and prepaid and cod["rto_rate_pct"] is not None and prepaid["rto_rate_pct"] is not None and cod["rto_rate_pct"] - prepaid["rto_rate_pct"] >= GAP_POINTS:
        found.append(f"Cash on delivery is where the returns are: {b(pct(cod['rto_rate_pct']))} of COD parcels came back, against {b(pct(prepaid['rto_rate_pct']))} of prepaid.")
        act.append("Move risky COD orders to prepaid. The Order risk checker scores each order, and the Returns report shows which zones, channels and pincodes to start with.")
    if len(months) > 1 and months[0]["rto_rate_pct"] is not None and months[-1]["rto_rate_pct"] is not None:
        first, last = months[0], months[-1]
        move = "fell" if last["rto_rate_pct"] < first["rto_rate_pct"] else "rose" if last["rto_rate_pct"] > first["rto_rate_pct"] else "stayed"
        found.append(f"The return rate {move} from {b(pct(first['rto_rate_pct']))} in {month_name(first['month'])} to {b(pct(last['rto_rate_pct']))} in {month_name(last['month'])}.")
    if a["findings"]:
        found.append(f"The couriers owe {b(inr(a['total_recoverable_inr']))} across {b(count(a['findings']))} {noun(a['findings'], 'charge')}: {inr(a['billing_overcharge_inr'])} overbilled on invoices and {inr(a['cod_missing_inr'])} of COD cash not paid over.")
        act.append(f"Send each courier its claim. The claim file on the Billing audit page lists all {count(a['findings'])} {noun(a['findings'], 'charge')} with the amount for each.")
    top, low = worst(couriers, "rto_rate_pct")
    if top and top["rto_rate_pct"] - low["rto_rate_pct"] >= GAP_POINTS:
        found.append(f"{b(name(top['courier']))} has the highest return rate at {b(pct(top['rto_rate_pct']))}, against {pct(low['rto_rate_pct'])} for {esc(name(low['courier']))}.")
        act.append(f"Review {esc(name(top['courier']))} with the Courier scorecard before sending it more parcels.")

    return render(title="Business summary", merchant_name=merchant.name, period=span, story=story, findings=found, actions=act, sources=sources(merchant),
                  covers="The headline numbers for the whole business: orders, revenue, returns, what couriers owe, and each courier at a glance. The other four reports go deeper into each part.",
                  method=["A parcel counts as returned when its final status is RTO, and as delivered when its final status is Delivered.",
                          "Delivered revenue is the order value of delivered parcels only.",
                          "Courier charges on returns are the amounts the courier billed for parcels that came back.",
                          "The amount recoverable is the sum of every disputed charge found by the billing audit."],
                  limits=LIMITS)


# ---------------------------------------------------------------- 2. returns
def returns_report(merchant):
    o = metrics.overview(merchant)
    span, months = period(merchant)
    per_parcel = o["rto_courier_cost_inr"] / o["rto"] if o["rto"] else None
    story = [*section("Overview", "Returns in four numbers"),
             tiles([("Return rate", pct(o["rto_rate_pct"]), f"{count(o['rto'])} of {count(o['total_shipments'])} {noun(o['total_shipments'], 'parcel')}"),
                    ("Courier charges on returns", inr(o["rto_courier_cost_inr"]), f"{inr(per_parcel)} per returned parcel"),
                    ("Value of returned orders", inr(o["rto_order_value_inr"]), "shipped and not kept"),
                    ("Share of parcels sent COD", pct(o["cod_share_pct"]), "")])]
    if len(months) > 1:
        story.append(together(section("Trend", "Return rate, month by month"), trend(months)))

    cuts = [("payment_mode", "Payment", "By payment", lambda v: "Cash on delivery" if v == "COD" else name(v)),
            ("first_order", "Customer", "First order against repeat order", lambda v: "First order" if v else "Repeat order"),
            ("zone", "Distance", "By delivery zone", lambda v: f"Zone {v}" if v else "No zone on file"),
            ("courier", "Courier", "By courier", lambda v: name(v, "Unknown courier")),
            ("sales_channel", "Channel", "By sales channel", name),
            ("city_tier", "City", "By city tier", lambda v: f"Tier {v}" if v else "Not recorded")]
    seen = {}
    for dim, kicker, title, label in cuts:
        rows = metrics.rto_by(merchant, dim)
        if len(rows) < 2:
            continue  # one group is not a comparison
        seen[dim] = (rows, label)
        story.append(together(
            section(kicker, title), chart(charts.bars([label(r[dim]) for r in rows], [r["rto_rate_pct"] or 0 for r in rows], flag_max=True)),
            table(["Group", "Parcels", "Returned", "Return rate", "COD share", "Courier charges on returns"],
                  [[label(r[dim]), count(r["shipments"]), count(r["rto"]), pct(r["rto_rate_pct"]), pct(r["cod_share_pct"]), inr(r["rto_courier_cost_inr"])] for r in rows],
                  [0.3, 0.12, 0.12, 0.14, 0.12, 0.2], right=(1, 2, 3, 4, 5))))

    pins = sorted(metrics.rto_by(merchant, "pincode", 30), key=lambda r: r["rto_courier_cost_inr"] or 0, reverse=True)[:20]
    if pins:
        story += [room(), *section("Places", f"The {len(pins)} pincodes where returns cost the most"),
                  para("Only pincodes with 30 parcels or more are listed, so one unlucky parcel cannot put a pincode on this page.", "note"), gap(2),
                  table(["Pincode", "Parcels", "Returned", "Return rate", "COD share", "Courier charges on returns"],
                        [[name(r["pincode"]), count(r["shipments"]), count(r["rto"]), pct(r["rto_rate_pct"]), pct(r["cod_share_pct"]), inr(r["rto_courier_cost_inr"])] for r in pins],
                        [0.2, 0.14, 0.14, 0.16, 0.14, 0.22], right=(1, 2, 3, 4, 5))]

    found, act = [], []
    if o["rto"]:
        found.append(f"{b(count(o['rto']))} {noun(o['rto'], 'parcel')} came back, {b(pct(o['rto_rate_pct']))} of everything sent. Each one cost {b(inr(per_parcel))} in courier charges on average.")
    said = {"payment_mode": ("{top} parcels come back most often: {a} against {z} for {low}.", "Ask for prepayment, or a part payment, on the COD orders the Order risk checker marks High or Very high."),
            "first_order": ("{top}s are the risk: {a} came back, against {z} for a {low}.", "Confirm first-time COD orders by phone or WhatsApp before they ship."),
            "zone": ("{top} has the highest return rate at {a}; {low} has the lowest at {z}.", "Think again about offering COD to {top}, where a return also costs the most to carry."),
            "courier": ("{top} returns the most parcels: {a}, against {z} for {low}.", "Compare {top} with your other couriers on the same zones before sending it more parcels."),
            "sales_channel": ("Orders from {top} come back most often: {a}, against {z} from {low}.", "Tighten checks on {top} orders: confirm the address and the intent to buy before shipping."),
            "city_tier": ("{top} cities return the most: {a}, against {z} in {low}.", None)}
    for dim, (finding, action) in said.items():
        if dim not in seen:
            continue
        rows, label = seen[dim]
        top, low = worst(rows, "rto_rate_pct", floor=30)
        if top and top["rto_rate_pct"] - low["rto_rate_pct"] >= GAP_POINTS:
            words = dict(top=esc(label(top[dim])), low=esc(label(low[dim])), a=b(pct(top["rto_rate_pct"])), z=pct(low["rto_rate_pct"]))
            found.append(finding.format(**words))
            if action:
                act.append(action.format(**words))
    if pins:
        cost = sum(r["rto_courier_cost_inr"] or 0 for r in pins)
        found.append(f"The {len(pins)} costliest pincodes account for {b(inr(cost))} of courier charges on returns.")
        act.append("Check the pincodes listed in this report first. A pincode with a high return rate and a high COD share is the clearest case for prepaid only.")

    return render(title="Returns report", merchant_name=merchant.name, period=span, story=story, findings=found, actions=act, sources=sources(merchant),
                  covers="Which parcels came back and what they have in common: how they were paid for, where they went, who carried them and where the order came from.",
                  method=["The return rate of a group is its returned parcels divided by all its parcels with a known outcome.",
                          "COD share is the part of a group's parcels that were sent cash on delivery. A group with a high COD share will show more returns for that reason alone.",
                          f"A group is only called worse than another when their return rates differ by {GAP_POINTS} points or more, and both have at least 30 parcels.",
                          "City tier and zone come from the pincode file. A pincode missing from that file shows as not recorded."],
                  limits=LIMITS + ["A higher return rate in one group does not prove that the group causes returns. Groups overlap: a far zone may also have more COD orders."])


# ---------------------------------------------------------------- 3. couriers
def courier_scorecard(merchant):
    span, _ = period(merchant)
    speed = metrics.delivery_by(merchant, "courier")
    rto = {r["courier"]: r for r in metrics.rto_by(merchant, "courier")}
    a = audit_summary(merchant)
    owed = {r["courier"]: r for r in a["by_courier"]}
    cod = metrics.cod_summary(merchant)
    label = lambda c: name(c, "Unknown courier")  # noqa: E731
    rows = [{**c, "rto_rate_pct": rto.get(c["courier"], {}).get("rto_rate_pct")} for c in speed]

    story = [*section("Scorecard", "Every courier, side by side"),
             table(["Courier", "Parcels", "Return rate", "Delivered", "On time", "First attempt", "Days to deliver", "Billed per parcel"],
                   [[label(c["courier"]), count(c["shipments"]), pct(c["rto_rate_pct"]), pct(c["delivered_rate_pct"]), pct(c["on_time_pct"]),
                     pct(c["first_attempt_delivery_pct"]), name(c["avg_delivery_days"], "-"), inr(c["avg_billed_per_shipment_inr"])] for c in rows],
                   [0.25, 0.1, 0.11, 0.11, 0.1, 0.11, 0.11, 0.11], right=range(1, 8))]
    if len(rows) > 1:
        names = [label(c["courier"]) for c in rows]
        story.append(together(section("Returns", "Return rate"), chart(charts.bars(names, [c["rto_rate_pct"] or 0 for c in rows], flag_max=True))))
        story.append(together(section("Reliability", "Delivered on time"), chart(charts.bars(names, [c["on_time_pct"] or 0 for c in rows], colour=charts.TEAL))))
        story.append(together(section("Speed", "Days from pickup to delivery"),
                              chart(charts.bars(names, [c["avg_delivery_days"] or 0 for c in rows], fmt=lambda v, _p=None: f"{v:.2f} days", flag_max=True))))
    if a["findings"]:
        story.append(together(section("Money owed", "What each courier owes you"),
                              table(["Courier", "Charges to dispute", "Amount to claim"],
                                    [[label(c), count(r["findings"]), inr(r["claim_inr"])] for c, r in owed.items()], [0.5, 0.25, 0.25], right=(1, 2))))
    if cod:
        story.append(together(section("COD cash", "Cash collected and paid over"),
                              table(["Courier", "COD parcels delivered", "Collected for you", "Paid to you", "Missing", "Never paid", "Paid short"],
                                    [[label(c["courier"]), count(c["cod_delivered_shipments"]), inr(c["cod_due_inr"]), inr(c["cod_remitted_inr"]), inr(c["gap_inr"]),
                                      count(c["not_remitted"]), count(c["short_paid"])] for c in cod], [0.24, 0.14, 0.15, 0.15, 0.12, 0.1, 0.1], right=range(1, 7))))

    found, act = [], []
    top, low = worst(rows, "rto_rate_pct")
    if top and top["rto_rate_pct"] - low["rto_rate_pct"] >= GAP_POINTS:
        found.append(f"{b(label(top['courier']))} returns the most parcels: {b(pct(top['rto_rate_pct']))}, against {pct(low['rto_rate_pct'])} for {esc(label(low['courier']))}.")
        act.append(f"Ask {esc(label(top['courier']))} why its return rate is higher, with the zone-by-zone figures from the RTO analytics page in hand.")
    timed = sorted((c for c in rows if c["on_time_pct"] is not None), key=lambda c: c["on_time_pct"])
    if len(timed) > 1 and timed[-1]["on_time_pct"] - timed[0]["on_time_pct"] >= GAP_POINTS:
        found.append(f"{b(label(timed[0]['courier']))} is on time least often: {b(pct(timed[0]['on_time_pct']))} of deliveries, against {pct(timed[-1]['on_time_pct'])} for {esc(label(timed[-1]['courier']))}.")
        act.append(f"Give time-sensitive orders to {esc(label(timed[-1]['courier']))} where it serves the pincode.")
    slow = sorted((c for c in rows if c["avg_delivery_days"] is not None), key=lambda c: c["avg_delivery_days"])
    if len(slow) > 1 and slow[-1]["avg_delivery_days"] - slow[0]["avg_delivery_days"] >= 0.5:
        found.append(f"{b(label(slow[-1]['courier']))} takes {b(slow[-1]['avg_delivery_days'])} days to deliver on average; {esc(label(slow[0]['courier']))} takes {slow[0]['avg_delivery_days']}.")
    if owed:
        most = max(owed.items(), key=lambda kv: kv[1]["claim_inr"])
        found.append(f"{b(label(most[0]))} owes the most: {b(inr(most[1]['claim_inr']))} across {count(most[1]['findings'])} {noun(most[1]['findings'], 'charge')}. All couriers together owe {inr(a['total_recoverable_inr'])}.")
        act.append("Raise the claims with each courier's account manager and ask for a credit note against the next invoice.")
    gaps = [c for c in cod if (c["gap_inr"] or 0) > 0]
    if gaps:
        most = max(gaps, key=lambda c: c["gap_inr"])
        found.append(f"{b(inr(sum(c['gap_inr'] for c in gaps)))} of COD cash is still with the couriers. {b(label(most['courier']))} holds the most, {inr(most['gap_inr'])}.")
        act.append("Chase the unpaid COD first. It is your own money, and it gets harder to recover as it gets older.")

    return render(title="Courier scorecard", merchant_name=merchant.name, period=span, story=story, findings=found, actions=act, sources=sources(merchant),
                  covers="How each courier performed on returns, speed and reliability, what each one billed, and what each one still owes.",
                  method=["On time means delivered on or before the date the courier promised.",
                          "First attempt is the share of delivered parcels that needed only one delivery attempt.",
                          "Days to deliver are counted from pickup to delivery, for delivered parcels only.",
                          "COD cash missing is what the courier collected on delivered COD parcels, less what its remittance statements show as paid."],
                  limits=LIMITS + ["Couriers do not carry the same mix of parcels. One that is given the far zones or more COD orders will look worse for that reason."])


# ---------------------------------------------------------------- 4. billing audit
TOP_FINDINGS = 60
FIX = {  # kind of error -> how to stop it happening again
    "weight_inflated": "Weigh and photograph parcels at packing, so a heavier billed weight can be disputed with proof.",
    "wrong_zone": "Ask the courier to share its pincode-to-zone list and compare it with yours.",
    "duplicate_line": "Ask the courier why the same AWB was billed twice, and check each new invoice for repeats before paying.",
    "rto_charge_not_due": "Do not pay return charges on parcels the courier's own report shows as delivered.",
    "cod_fee_not_due": "Ask the courier to remove COD fees from prepaid parcels at source.",
    "cod_not_remitted": "Reconcile COD every remittance cycle, parcel by parcel, instead of trusting the total.",
    "cod_short_paid": "Ask for the deduction behind each short payment in writing.",
}


def audit_report(merchant):
    span, _ = period(merchant)
    a = audit_summary(merchant)
    story = [*section("Overview", "The claim in four numbers"),
             tiles([("Recoverable from couriers", inr(a["total_recoverable_inr"]), f"{count(a['findings'])} {noun(a['findings'], 'charge')} to dispute"),
                    ("Overcharged on invoices", inr(a["billing_overcharge_inr"]), f"{count(a['billing_findings'])} {noun(a['billing_findings'], 'line')}, {pct(a['overcharge_pct_of_billed'])} of everything billed"),
                    ("COD cash not paid to you", inr(a["cod_missing_inr"]), f"{count(a['cod_findings'])} delivered parcels"),
                    ("Billed by couriers", inr(a["total_courier_billed_inr"]), "checked line by line")])]
    found, act = [], []
    kinds = a["by_kind"]
    if not a["findings"]:
        story += [gap(), callout("Every invoice line and every COD payment checked out against your own data. There is nothing to dispute.")]
        found.append("No overcharge and no missing COD payment was found in the uploaded invoices and remittance statements.")
    else:
        story.append(together(section("By error", "The claim, by kind of error"),
                              chart(charts.bars([k["label"] for k in kinds], [k["claim_inr"] for k in kinds], fmt=charts.rupees, colour=charts.TEAL)),
                              table(["Kind of error", "Charges", "Amount to claim"], [[k["label"], count(k["findings"]), inr(k["claim_inr"])] for k in kinds], [0.6, 0.18, 0.22], right=(1, 2))))
        story.append(together(section("By courier", "The claim, by courier"),
                              table(["Courier", "Charges", "Amount to claim"], [[name(c["courier"]), count(c["findings"]), inr(c["claim_inr"])] for c in a["by_courier"]], [0.6, 0.18, 0.22], right=(1, 2))))
        story += [room(), *section("Detail", "Each courier, by kind of error"),
                  table(["Courier", "Kind of error", "Charges", "Amount to claim"],
                        [[name(r["courier"]), r["label"], count(r["findings"]), inr(r["claim_inr"])] for r in a["by_courier_kind"]], [0.28, 0.42, 0.12, 0.18], right=(2, 3))]
        top = list(audit_findings(merchant)[:TOP_FINDINGS])
        labels = {k["kind"]: k["label"] for k in kinds}
        partial = a["findings"] > len(top)
        story += [room(), *section("Charges", f"The {len(top)} largest charges" if partial else "Every charge"),
                  para(f"The largest {len(top)} of {count(a['findings'])} {noun(a['findings'], 'charge')} are listed. The claim file (CSV) on the Billing audit page has every one, ready to send to each courier.", "note") if partial else gap(0),
                  gap(2),
                  table(["Courier", "AWB", "What is wrong", "Billed", "Should be", "Claim"],
                        [[f.courier_name, f.awb_number, f"{labels.get(f.kind, f.kind)}. {f.detail}", inr(float(f.billed_inr)), inr(float(f.expected_inr)), inr(float(f.claim_inr))] for f in top],
                        [0.16, 0.15, 0.36, 0.1, 0.12, 0.11], right=(3, 4, 5))]

        found.append(f"The couriers owe {b(inr(a['total_recoverable_inr']))} across {b(count(a['findings']))} {noun(a['findings'], 'charge')}.")
        if a["billing_findings"]:
            found.append(f"{b(pct(a['overcharge_pct_of_billed']))} of everything billed was an overcharge: {b(inr(a['billing_overcharge_inr']))} on {count(a['billing_findings'])} invoice {noun(a['billing_findings'], 'line')}.")
        if a["cod_findings"]:
            found.append(f"{b(inr(a['cod_missing_inr']))} of COD cash, collected on {count(a['cod_findings'])} delivered parcels, has not reached you.")
        big = kinds[0]
        found.append(f"The largest kind of error is “{esc(big['label'])}”: {b(inr(big['claim_inr']))} on {count(big['findings'])} {noun(big['findings'], 'parcel')}.")
        if a["by_courier"]:
            c = a["by_courier"][0]
            found.append(f"{b(name(c['courier']))} owes the most: {b(inr(c['claim_inr']))}.")
        act.append(f"Download the claim file from the Billing audit page and send each courier its own rows. It has all {count(a['findings'])} {noun(a['findings'], 'charge')} with the billed amount, the correct amount and the reason.")
        for k in kinds[:3]:
            if FIX.get(k["kind"]):
                act.append(FIX[k["kind"]])

    return render(title="Billing audit and claims", merchant_name=merchant.name, period=span, story=story, findings=found, actions=act, sources=sources(merchant),
                  covers="Every courier invoice line and every COD payment, checked against your own rate card and shipment records, and the amount you can claim back.",
                  method=["The correct charge for a parcel is worked out from your rate card: the chargeable weight (the higher of actual and volumetric weight, in 500 g steps), the zone, any COD fee and any return charge, plus 18% GST.",
                          "A line is disputed only when it is more than ₹1 above the correct charge, and the reason can be named.",
                          "A delivered COD parcel counts as unpaid when no remittance covers it 21 days after delivery, and as short paid when the remittance is less than the amount collected.",
                          "An AWB billed on more than one invoice line is disputed from the second line onward."],
                  limits=LIMITS + ["The audit can only be as right as the rate card uploaded. If a rate was renegotiated and the file was not updated, some charges will be flagged wrongly.",
                                   "A charge listed here is a reasoned claim, not a settled amount. The courier may hold records that explain it."])


# ---------------------------------------------------------------- 5. customers
def customer_report(merchant):
    span, _ = period(merchant)
    segs = segment_summary(merchant)
    by = {s["segment"]: s for s in segs}
    everyone = sum(s["customers"] for s in segs)
    scored = [s for s in segs if s["rto_rate_pct"] is not None]
    story = [*section("Overview", "Who your customers are"),
             para(f"{b(count(everyone))} {noun(everyone, 'customer')} {noun(everyone, 'has', 'have')} placed an order. They are grouped by what happened to their parcels.")]
    if scored:
        story.append(together(gap(2), chart(charts.paired([s["segment"] for s in scored], [s["customer_share_pct"] or 0 for s in scored],
                                                          [s["revenue_share_pct"] or 0 for s in scored], names=("Share of customers", "Share of delivered revenue")))))
    story += [room(), *section("Segments", "The groups, and what each one means"),
              table(["Segment", "What it means", "Customers", "Return rate", "COD return rate", "Delivered value", "Share of revenue"],
                    [[s["segment"], s["meaning"], count(s["customers"]), pct(s["rto_rate_pct"]), pct(s["cod_rto_rate_pct"]), inr(s["delivered_value_inr"]), pct(s["revenue_share_pct"])]
                     for s in segs], [0.14, 0.27, 0.12, 0.1, 0.11, 0.14, 0.12], right=(2, 3, 4, 5, 6))]

    t = customer_table(merchant)
    cols = ["Customer", "ID", "Pincode", "Parcels", "Returned", "Return rate", "Delivered value"]
    widths, right = [0.26, 0.13, 0.11, 0.1, 0.11, 0.12, 0.17], (3, 4, 5, 6)

    def rows(frame):
        return [[name(r["name"], r["customer_ref"]), r["customer_ref"], name(r["pincode"], "-"), count(r["parcels"]), count(r["returned"]), pct(r["rto_rate_pct"]), inr(r["delivered_value"])]
                for r in frame.to_dict("records")]

    returners = t[t["segment"] == "Repeat returner"].sort_values(["returned", "rto_rate_pct"], ascending=False).head(25)
    if len(returners):
        story += [room(), *section("Watch list", f"The {len(returners)} customers who returned the most parcels"), table(cols, rows(returners), widths, right)]
    loyal = t[t["segment"] == "Loyal"].sort_values("delivered_value", ascending=False).head(25)
    if len(loyal):
        story += [room(), *section("Best customers", f"Your {len(loyal)} most valuable loyal customers"), table(cols, rows(loyal), widths, right)]

    found, act = [], []
    rr, loy, first = by.get("Repeat returner"), by.get("Loyal"), by.get("Returned first order")
    if loy and loy["customers"]:
        found.append(f"{b(count(loy['customers']))} loyal {noun(loy['customers'], 'customer')}, {b(pct(loy['customer_share_pct']))} of all customers, brought in {b(pct(loy['revenue_share_pct']))} of delivered revenue.")
        act.append("Look after the loyal group first: early access, a thank-you offer, and cash on delivery without checks. They accept almost everything they order.")
    if rr and rr["customers"]:
        found.append(f"{b(count(rr['customers']))} {noun(rr['customers'], 'customer is a repeat returner', 'customers are repeat returners')}. {b(pct(rr['rto_rate_pct']))} of their parcels came back"
                     + (f", and {b(pct(rr['cod_rto_rate_pct']))} of their COD parcels." if rr["cod_rto_rate_pct"] is not None else "."))
        act.append("Offer repeat returners prepaid only. The watch list in this report names the ones who returned the most.")
    if first and first["customers"]:
        found.append(f"{b(count(first['customers']))} {noun(first['customers'], 'customer')} returned the only parcel they were ever sent.")
        act.append("Confirm a first COD order by phone or WhatsApp before shipping it. A first order is the one most likely to come back.")
    if not found:
        found.append("Too few parcels have an outcome yet to tell one group of customers from another.")

    return render(title="Customer report", merchant_name=merchant.name, period=span, story=story, findings=found, actions=act, sources=sources(merchant),
                  covers="Your customers in groups, by what happened to their parcels: who accepts, who returns, and how much of your revenue each group brings.",
                  method=["A customer is matched across orders by customer ID, or by phone number when no ID is given. Phone numbers are stored only in scrambled form and never appear in a report.",
                          "A repeat returner has had at least 2 parcels come back and at least 30% of everything sent to them.",
                          "A loyal customer has received 4 or more parcels and accepted almost all of them.",
                          "Delivered value counts only the orders that were delivered and kept."],
                  limits=LIMITS + ["Two people sharing one phone number, or one person using two, are counted as the data shows them."])


# ---------------------------------------------------------------- the catalogue
REPORTS = {
    "summary": ("Business summary", "The headline numbers: orders, revenue, returns, courier claims and each courier at a glance.", business_summary, "outcomes"),
    "returns": ("Returns report", "Where returns come from: month by month, then by payment, zone, courier, channel and city tier, and the pincodes that cost the most.", returns_report, "outcomes"),
    "couriers": ("Courier scorecard", "Every courier side by side on returns, speed and billing, with what each one owes you and the COD cash it still holds.", courier_scorecard, "outcomes"),
    "audit": ("Billing audit and claims", "The total you can claim, split by kind of error and by courier, with the largest disputed charges listed.", audit_report, "invoices"),
    "customers": ("Customer report", "Your customers in segments, the ones who return the most, and the loyal ones worth the most.", customer_report, "customers"),
}


def catalogue(merchant):
    """Each report with whether this merchant has the data for it. Decided from real rows, never from zeros in a metric."""
    have = {
        "outcomes": ShipmentLedger.objects.for_merchant(merchant).exists() and metrics.overview(merchant)["total_shipments"] > 0,
        "invoices": InvoiceLine.objects.for_merchant(merchant).exists() and Shipment.objects.for_merchant(merchant).exists(),
        "customers": Order.objects.for_merchant(merchant).exists(),
    }
    why = {"outcomes": "Import shipments with a final outcome (delivered or returned) to build this report.",
           "invoices": "Import courier invoices and shipments to build this report.", "customers": "Import your orders to build this report."}
    return [{"id": key, "title": title, "description": text, "available": bool(have[need]), "reason": None if have[need] else why[need]}
            for key, (title, text, _build, need) in REPORTS.items()]
