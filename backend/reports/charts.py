"""Matplotlib charts for the PDF reports. Each function returns PNG bytes; nothing is written to disk.

Colour is used sparingly: navy for the data, one deep red to mark the worst value, grey for a second series."""
import io
import os
import textwrap

import matplotlib

matplotlib.use("Agg")  # no display: charts are drawn straight to memory, which is what a web server needs
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

FONTS = os.path.join(os.path.dirname(__file__), "fonts")
for _f in ("Inter-Regular.ttf", "Inter-SemiBold.ttf"):
    font_manager.fontManager.addfont(os.path.join(FONTS, _f))

NAVY, TEAL, RED = "#0a2540", "#0f5c56", "#9b1c1c"
SLATE, MUTED, RULE = "#475569", "#a8b3c4", "#e3e8ef"

plt.rcParams.update({
    "font.family": "Inter", "font.size": 9, "text.color": NAVY, "axes.labelcolor": SLATE,
    "axes.edgecolor": RULE, "xtick.color": SLATE, "ytick.color": SLATE,
    "axes.spines.top": False, "axes.spines.right": False,
})


def _png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)  # a long-running server must free every figure it draws
    return buf.getvalue()


def rupees(v, _pos=None):
    """Short Indian money for a chart: 1,50,000 -> ₹1.5 L."""
    a = abs(v)
    if a >= 1e7:
        return f"₹{v / 1e7:.1f} Cr"
    if a >= 1e5:
        return f"₹{v / 1e5:.1f} L"
    if a >= 1e3:
        return f"₹{v / 1e3:.0f}k"
    return f"₹{v:.0f}"


def percent(v, _pos=None):
    return f"{v:.0f}%"


def percent1(v, _pos=None):
    return f"{v:.1f}%"


def line(labels, values, *, fmt=percent, width=6.7, height=2.5):
    """One series over time, with the first and last points labelled. Axis labels are thinned so they never overlap."""
    fig, ax = plt.subplots(figsize=(width, height))
    xs = list(range(len(values)))
    ax.plot(xs, values, color=NAVY, linewidth=2)
    ax.fill_between(xs, values, color=NAVY, alpha=0.06)
    for i in sorted({0, len(xs) - 1}):
        ax.scatter([xs[i]], [values[i]], color=NAVY, zorder=3, s=20)
        ax.annotate(percent1(values[i]) if fmt is percent else fmt(values[i]), (xs[i], values[i]), textcoords="offset points",
                    xytext=(0, 8), ha="left" if i == 0 else "right", fontsize=8.5, fontweight="semibold", color=NAVY)
    step = max(1, len(labels) // 8)
    ax.set_xticks(xs[::step])
    ax.set_xticklabels(labels[::step])
    ax.yaxis.set_major_formatter(FuncFormatter(fmt))
    ax.set_ylim(0, max(values) * 1.18 if values and max(values) else 1)
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    for side in ("left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    return _png(fig)


def bars(labels, values, *, fmt=percent1, colour=NAVY, flag_max=False, width=6.7, row=0.36):
    """Horizontal bars, first label on top, each bar labelled with its value.
    With flag_max the largest bar is drawn in red and the rest in navy."""
    n = len(values)
    fig, ax = plt.subplots(figsize=(width, max(1.1, row * n + 0.35)))
    top = max(values) if values else 0
    colours = [RED if flag_max and n > 1 and v == top else colour for v in values]
    ys = list(range(n))[::-1]
    ax.barh(ys, values, color=colours, height=0.56)
    ax.set_yticks(ys)
    ax.set_yticklabels([textwrap.shorten(str(x), 46, placeholder="…") for x in labels])
    for y, v in zip(ys, values):
        ax.text(v + top * 0.012, y, fmt(v), va="center", fontsize=8.5, fontweight="semibold", color=NAVY)
    ax.set_xlim(0, top * 1.16 if top else 1)
    ax.xaxis.set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    return _png(fig)


def paired(labels, left, right, *, names, fmt=percent, width=6.7, height=2.7):
    """Two bars per label, side by side: e.g. share of customers against share of revenue."""
    fig, ax = plt.subplots(figsize=(width, height))
    xs = list(range(len(labels)))
    w = 0.36
    for offset, values, colour, name in ((-w / 2, left, MUTED, names[0]), (w / 2, right, NAVY, names[1])):
        rects = ax.bar([x + offset for x in xs], values, width=w, color=colour, label=name)
        for r, v in zip(rects, values):
            ax.text(r.get_x() + r.get_width() / 2, v, fmt(v), ha="center", va="bottom", fontsize=8, color=NAVY)
    ax.set_xticks(xs)
    ax.set_xticklabels([textwrap.fill(str(x), 14) for x in labels], fontsize=8)  # long names wrap instead of colliding
    ax.yaxis.set_major_formatter(FuncFormatter(fmt))
    ax.set_ylim(0, max([*left, *right, 1]) * 1.14)  # headroom for the value above the tallest bar
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    for side in ("left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.legend(frameon=False, fontsize=8, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2)  # above the plot, clear of the bars
    return _png(fig)
