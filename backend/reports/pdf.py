"""Page layout for the PDF reports.

Every report has the same three parts: an introduction page, the report itself, and a conclusion page.
The look uses two deep colours (navy and teal) on white, with one deep red kept for the worst value."""
import io
import os

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

# Inter is the typeface the website uses. It has a rupee sign, which ReportLab's built-in fonts do not.
# The two weights live in reports/fonts/ with their licence (SIL Open Font License).
_FONTS = os.path.join(os.path.dirname(__file__), "fonts")
pdfmetrics.registerFont(TTFont("Body", os.path.join(_FONTS, "Inter-Regular.ttf")))
pdfmetrics.registerFont(TTFont("Body-Bold", os.path.join(_FONTS, "Inter-SemiBold.ttf")))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body", boldItalic="Body-Bold")

NAVY, TEAL, RED = (colors.HexColor(c) for c in ("#0a2540", "#0f5c56", "#9b1c1c"))
SLATE, RULE, MIST = (colors.HexColor(c) for c in ("#475569", "#e3e8ef", "#f4f6fa"))
SIDE = 20 * mm
WIDTH = A4[0] - 2 * SIDE  # the printable width between the side margins
COVER = 70 * mm           # height of the navy band on the first page


def _style(name, **kw):
    base = dict(fontName="Body", fontSize=9.5, leading=14.5, textColor=NAVY)
    return ParagraphStyle(name, **{**base, **kw})


S = {
    "kicker": _style("kicker", fontName="Body-Bold", fontSize=7.5, leading=10, textColor=TEAL, spaceBefore=12, spaceAfter=2),
    "h2": _style("h2", fontName="Body-Bold", fontSize=13.5, leading=17, spaceAfter=6),
    "h3": _style("h3", fontName="Body-Bold", fontSize=10.5, leading=14, spaceBefore=8, spaceAfter=3),
    "body": _style("body"),
    "lead": _style("lead", fontSize=11, leading=17),
    "note": _style("note", fontSize=8, leading=11.5, textColor=SLATE),
    "cell": _style("cell", fontSize=8.5, leading=11.5),
    "cell_r": _style("cell_r", fontSize=8.5, leading=11.5, alignment=TA_RIGHT),
    "head": _style("head", fontName="Body-Bold", fontSize=7, leading=9.5, textColor=SLATE),
    "head_r": _style("head_r", fontName="Body-Bold", fontSize=7, leading=9.5, textColor=SLATE, alignment=TA_RIGHT),
    "tile_label": _style("tile_label", fontSize=7.5, leading=10, textColor=SLATE),
    "tile_value": _style("tile_value", fontName="Body-Bold", fontSize=14, leading=18),
    "num": _style("num", fontName="Body-Bold", fontSize=13, leading=16, textColor=TEAL),
}


# ---------------------------------------------------------------- number formats (Indian digit grouping)
def count(n):
    if n is None:
        return "-"
    s = str(abs(int(round(n))))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        s = ",".join(([head] if head else []) + groups + [tail])
    return ("-" if n < 0 else "") + s


def inr(n):
    return "-" if n is None else f"₹{count(n)}"


def pct(n):
    return "-" if n is None else f"{n:.1f}%"


def esc(text):
    """Merchant data goes into Paragraphs, which read a small markup language. Escape it."""
    return str(text if text is not None else "-").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------- building blocks
def section(kicker, title):
    """A section heading: a small teal label over the title."""
    return [Paragraph(esc(kicker).upper(), S["kicker"]), Paragraph(esc(title), S["h2"])]


def h3(text):
    return Paragraph(esc(text), S["h3"])


def para(text, style="body"):
    """`text` may carry <b> tags written by this code. Merchant values must be passed through esc() first."""
    return Paragraph(text, S[style])


def gap(mm_=3):
    return Spacer(1, mm_ * mm)


def room(mm_=55):
    """Start a new page unless this much space is left. Put it before the heading of a long table,
    so the heading always has rows under it."""
    return CondPageBreak(mm_ * mm)


def together(*parts):
    """Keep a heading with what follows it, so a heading is never left alone at the foot of a page."""
    flat = []
    for p in parts:
        flat.extend(p if isinstance(p, list) else [p])
    return KeepTogether(flat)


def tiles(items):
    """A row of headline numbers. items: [(label, value, note), ...], up to four.
    Each tile is a pale block with a navy line across its top."""
    n = len(items)
    space = 3 * mm
    w = (WIDTH - space * (n - 1)) / n
    cells, widths = [], []
    for i, (label, value, note) in enumerate(items):
        if i:
            cells.append("")
            widths.append(space)
        cells.append([Paragraph(esc(label), S["tile_label"]), Paragraph(esc(value), S["tile_value"]), Paragraph(esc(note or ""), S["note"])])
        widths.append(w)
    t = Table([cells], colWidths=widths)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
             ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]
    for i in range(n):
        c = i * 2
        style += [("BACKGROUND", (c, 0), (c, 0), MIST), ("LINEABOVE", (c, 0), (c, 0), 1.6, NAVY), ("LEFTPADDING", (c, 0), (c, 0), 8),
                  ("RIGHTPADDING", (c, 0), (c, 0), 6), ("TOPPADDING", (c, 0), (c, 0), 8), ("BOTTOMPADDING", (c, 0), (c, 0), 8)]
    t.setStyle(TableStyle(style))
    return t


def table(head, rows, widths, right=()):
    """A data table. `widths` are fractions of the page width; `right` lists the columns to right-align.
    The heading row repeats on every page the table runs onto."""
    def cell(v, i, top=False):
        style = ("head_r" if top else "cell_r") if i in right else ("head" if top else "cell")
        return Paragraph(esc(v).upper() if top else esc(v), S[style])

    data = [[cell(h, i, True) for i, h in enumerate(head)]] + [[cell(v, i) for i, v in enumerate(r)] for r in rows]
    t = Table(data, colWidths=[WIDTH * w for w in widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 1, NAVY), ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]))
    return t


def chart(png, width=WIDTH):
    """Place a chart's PNG bytes at the given width, keeping its shape."""
    img = Image(io.BytesIO(png))
    img.drawHeight = img.imageHeight * width / img.imageWidth
    img.drawWidth = width
    return img


def callout(text):
    """A pale block with a teal line down its left edge, for the one sentence a page is about."""
    t = Table([[Paragraph(text, S["body"])]], colWidths=[WIDTH])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), MIST), ("LINEBEFORE", (0, 0), (0, -1), 2.2, TEAL), ("LEFTPADDING", (0, 0), (-1, -1), 11),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return t


def numbered(items):
    """A numbered list: a teal number, then the text. Used for findings and next steps."""
    rows = [[Paragraph(f"{i:02d}", S["num"]), Paragraph(text, S["body"])] for i, text in enumerate(items, 1)]
    t = Table(rows, colWidths=[12 * mm, WIDTH - 12 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE)]))
    return t


ABOUT = ("logis is built on one idea: an online seller already holds the files that show where shipping money is lost. "
         "The order export, the courier's shipment report, the courier invoices, the rate card and the COD remittance statements "
         "are joined into one record for each parcel. From that record logis works out which parcels came back, what each return cost, "
         "whether each courier bill matches the agreed rate, and whether the cash collected at the door was paid over.")

GLOSSARY = [
    ("RTO", "Return to origin: a parcel the customer did not accept, sent back. The seller pays the courier both ways."),
    ("COD", "Cash on delivery: the courier collects the money at the door and pays it to the seller later."),
    ("AWB", "Air waybill number. The courier's tracking number for one parcel."),
    ("Zone", "The courier's pricing band for a route, from A (same city) to E (the farthest and costliest)."),
]


def render(*, title, merchant_name, period, covers, sources, method, story, findings, actions, limits):
    """Lay a report out on A4 and return the PDF as bytes.

    Page 1 is the introduction: what logis is built on, what this report covers, the data behind it and how the
    numbers are worked out. The report follows. The last page is the conclusion: what the data shows, what to do
    next, and the limits of the report. Every page after the first carries the report's name, the merchant, and a page number."""
    made = timezone.localtime().strftime("%d %b %Y, %H:%M")

    def cover(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, A4[1] - COVER, A4[0], COVER, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.rect(SIDE, A4[1] - 19 * mm, 3.4 * mm, 3.4 * mm, stroke=0, fill=1)
        canvas.setFont("Body-Bold", 11)
        canvas.drawString(SIDE + 5.6 * mm, A4[1] - 18.4 * mm, "logis")
        canvas.setFont("Body", 8)
        canvas.setFillColor(colors.HexColor("#a8b3c4"))
        canvas.drawRightString(A4[0] - SIDE, A4[1] - 18.4 * mm, "Logistics, worry-free.")
        canvas.setFillColor(colors.white)
        canvas.setFont("Body-Bold", 27)
        canvas.drawString(SIDE, A4[1] - 44 * mm, title)
        canvas.setFont("Body", 11)
        canvas.setFillColor(colors.HexColor("#d5dbe6"))
        canvas.drawString(SIDE, A4[1] - 52.5 * mm, merchant_name[:70])
        canvas.setFont("Body", 9)
        canvas.setFillColor(colors.HexColor("#a8b3c4"))
        canvas.drawString(SIDE, A4[1] - 60 * mm, f"{period}   ·   generated {made}")
        footer(canvas, doc)
        canvas.restoreState()

    def footer(canvas, doc):
        canvas.setFont("Body", 7.5)
        canvas.setFillColor(SLATE)
        canvas.drawString(SIDE, 11 * mm, "Figures come from the files uploaded to this workspace.")
        canvas.drawRightString(A4[0] - SIDE, 11 * mm, f"{doc.page}")

    def later(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(SIDE, A4[1] - 15.2 * mm, 2.8 * mm, 2.8 * mm, stroke=0, fill=1)
        canvas.setFont("Body-Bold", 9)
        canvas.drawString(SIDE + 4.6 * mm, A4[1] - 14.7 * mm, "logis")
        canvas.setFont("Body", 7.5)
        canvas.setFillColor(SLATE)
        canvas.drawRightString(A4[0] - SIDE, A4[1] - 14.7 * mm, f"{title}   ·   {merchant_name[:60]}")
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.6)
        canvas.line(SIDE, A4[1] - 18 * mm, A4[0] - SIDE, A4[1] - 18 * mm)
        footer(canvas, doc)
        canvas.restoreState()

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=SIDE, rightMargin=SIDE, title=f"{title} - {merchant_name}", author="logis")
    bottom = 19 * mm
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[Frame(SIDE, bottom, WIDTH, A4[1] - COVER - bottom - 6 * mm, id="c", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=cover),
        PageTemplate(id="page", frames=[Frame(SIDE, bottom, WIDTH, A4[1] - 23 * mm - bottom, id="p", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=later),
    ])

    # The data behind it: two files to a row, so the whole introduction fits on the first page.
    pairs = [[a, count(n)] for a, n in sources]
    if len(pairs) % 2:
        pairs.append(["", ""])
    half = len(pairs) // 2
    data_rows = [pairs[i] + pairs[i + half] for i in range(half)]
    intro = [NextPageTemplate("page"),
             *section("Introduction", "What this report is based on"), para(ABOUT),
             h3("What this report covers"), para(esc(covers)),
             h3("The data behind it"),
             table(["Uploaded file", "Rows", "Uploaded file", "Rows"], data_rows, [0.33, 0.15, 0.37, 0.15], right=(1, 3)),
             h3("How the numbers are worked out"),
             *[para(f"•&nbsp;&nbsp;{m}", "note") for m in method],
             h3("Words used in this report"),
             table(["Term", "Meaning"], GLOSSARY, [0.1, 0.9]),
             PageBreak()]

    end = [PageBreak(), *section("Conclusion", "What the data shows"),
           numbered(findings) if findings else para("There is not enough data yet to draw a conclusion."),
           *section("Next steps", "What to do about it"),
           numbered(actions) if actions else para("No action stands out from this data."),
           *section("Limits", "What this report cannot tell you"),
           *[para(f"•&nbsp;&nbsp;{x}", "note") for x in limits]]

    doc.build(intro + story + end)
    return buf.getvalue()
