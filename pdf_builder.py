# build_pdf.py — robust, non-overlapping PDF (ReportLab + Matplotlib)
# pip install reportlab matplotlib pillow

import io, json, textwrap
from pathlib import Path
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

INFILE = Path("report.json")
OUTFILE = Path("report.pdf")

# ---------- helpers ----------
def wrap_label(s, width=22):
    return "\n".join(textwrap.wrap(str(s), width=width)) if s else ""

def save_fig_to_buf(fig, dpi=200):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf

def make_rl_image(buf, max_w_mm, max_h_mm, assumed_dpi=200):
    """
    Scale an in-memory PNG to fit within max width/height (mm), preserving aspect.
    Prevents 'Flowable too large' LayoutError.
    """
    buf.seek(0)
    im = PILImage.open(buf)
    w_px, h_px = im.size
    w_pt = w_px * 72.0 / assumed_dpi
    h_pt = h_px * 72.0 / assumed_dpi
    max_w_pt = max_w_mm * mm
    max_h_pt = max_h_mm * mm
    scale = min(max_w_pt / w_pt, max_h_pt / h_pt, 1.0)
    return Image(buf, width=w_pt * scale, height=h_pt * scale)

def risk_color(risk):
    return {"LOW": colors.HexColor("#43a047"),
            "MEDIUM": colors.HexColor("#fb8c00"),
            "HIGH": colors.HexColor("#e53935")}.get(risk, colors.black)

def mpl_risk_color(risk):
    return {"LOW": "#43a047", "MEDIUM": "#fb8c00", "HIGH": "#e53935"}.get(risk, "#333333")

# ---------- charts (bounded heights) ----------
def chart_domain_scores(domains):
    names = [d["name"] for d in domains] or ["—"]
    scores = [int(d["score"]) for d in domains] or [0]
    # Bound the figure height so it never explodes
    h = min(4.8, max(2.2, 0.32 * len(names)))
    fig, ax = plt.subplots(figsize=(8, h), constrained_layout=True)
    y = range(len(names))
    ax.barh(y, scores)
    ax.set_yticks(y)
    ax.set_yticklabels([wrap_label(n, 24) for n in names])
    ax.invert_yaxis()
    ax.set_xlabel("Score")
    ax.set_xlim(left=0)
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    if scores:
        m = max(scores) or 1
        for i, v in enumerate(scores):
            ax.text(v + m * 0.02, i, str(v), va="center", fontsize=8)
    ax.set_title("Domain scores")
    return save_fig_to_buf(fig)

def chart_risk_heatmap(domains):
    names = [d["name"] for d in domains] or ["—"]
    risks = [d["risk"] for d in domains] or ["LOW"]
    vals = [1] * len(names)
    h = min(4.8, max(2.2, 0.32 * len(names)))
    fig, ax = plt.subplots(figsize=(8, h), constrained_layout=True)
    y = range(len(names))
    colors_bar = [mpl_risk_color(r) for r in risks]
    ax.barh(y, vals, color=colors_bar)
    ax.set_yticks(y)
    ax.set_yticklabels([wrap_label(n, 24) for n in names])
    ax.invert_yaxis()
    ax.set_xlabel("Risk bucket")
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    for i, r in enumerate(risks):
        ax.text(0.02, i, r, va="center", ha="left",
                color="white" if r != "LOW" else "black", fontweight="bold", fontsize=8)
    ax.set_title("Risk buckets")
    return save_fig_to_buf(fig)

def chart_top_items(top_items):
    if not top_items:
        fig, ax = plt.subplots(figsize=(8, 2.2), constrained_layout=True)
        ax.text(0.5, 0.5, "No high-scoring items", ha="center", va="center")
        ax.axis("off")
        return save_fig_to_buf(fig)
    labels = [wrap_label(f'{it.get("domain","")}: {it.get("answer","")}', 32) for it in top_items]
    vals = [int(it.get("points", 0)) for it in top_items]
    h = min(4.5, max(2.2, 0.36 * len(labels)))
    fig, ax = plt.subplots(figsize=(8, h), constrained_layout=True)
    y = range(len(labels))
    ax.barh(y, vals)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("Points")
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    m = max(vals) or 1
    for i, v in enumerate(vals):
        ax.text(v + m * 0.02, i, str(v), va="center", fontsize=8)
    ax.set_title("Top items")
    return save_fig_to_buf(fig)

# ---------- PDF build ----------
def build_pdf(data):
    pagesize = landscape(A4)
    doc = SimpleDocTemplate(
        str(OUTFILE),
        pagesize=pagesize,
        leftMargin=14*mm, rightMargin=14*mm, topMargin=12*mm, bottomMargin=12*mm,
        title="Competition Risk Diagnostic"
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=20, spaceAfter=8)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=14, spaceBefore=6, spaceAfter=6)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10, leading=13)
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=9, textColor=colors.grey)

    story = []
    # Header
    story.append(Paragraph(f'{data.get("organisation","Report")}', h1))
    story.append(Paragraph("Antitrust / Competition Risk Dashboard", h2))
    story.append(Paragraph(f'Completed by: {data.get("completed_by","")} — Generated: {data.get("generated_at","")}', small))
    story.append(Spacer(1, 6))

    # Summary badges
    overall = data.get("overall_risk", "LOW")
    total = int(data.get("total_score", 0))
    badge = Table(
        [[Paragraph(f'<b>Overall risk:</b> <font color="{risk_color(overall).hexval()}">{overall}</font>', body),
          Paragraph(f"<b>Total score:</b> {total}", body)]],
        colWidths=[120*mm, 60*mm]
    )
    badge.setStyle(TableStyle([("BOX", (0,0), (-1,-1), 0.5, colors.grey),
                               ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                               ("LEFTPADDING", (0,0), (-1,-1), 6),
                               ("RIGHTPADDING", (0,0), (-1,-1), 6)]))
    story.append(badge)
    story.append(Spacer(1, 8))

    # Charts — STACKED (avoid side-by-side tables to prevent LayoutError)
    domains = data.get("domains", [])
    img = make_rl_image(chart_risk_heatmap(domains), max_w_mm=270, max_h_mm=85)
    story.append(img); story.append(Spacer(1, 6))
    img = make_rl_image(chart_domain_scores(domains), max_w_mm=270, max_h_mm=95)
    story.append(img); story.append(Spacer(1, 6))

    story.append(Paragraph("Top items", h2))
    img = make_rl_image(chart_top_items(data.get("top_items", [])), max_w_mm=270, max_h_mm=95)
    story.append(img); story.append(Spacer(1, 8))

    # Per-domain details
    story.append(PageBreak())
    story.append(Paragraph("Per-domain details", h2))
    for d in domains:
        story.append(Paragraph(f'{d["name"]} — {d.get("risk","")}',
                               ParagraphStyle("dom", parent=h2, textColor=risk_color(d.get("risk","LOW")))))
        items = d.get("items", [])
        if not items:
            story.append(Paragraph("• —", body))
            continue
        rows = [["Question", "Answer", "Points"]]
        for it in items:
            q = wrap_label(it.get("question",""), 80)
            a = wrap_label(it.get("answer",""), 45)
            p = str(int(it.get("points", 0)))
            rows.append([q, a, p])
        tbl = Table(rows, colWidths=[160*mm, 90*mm, 20*mm], repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f0f0f0")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.HexColor("#333333")),
            ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#cccccc")),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (-1,-1), 4),
            ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 6))

    doc.build(story)
    print(f"Saved {OUTFILE.resolve()}")

# ---------- run ----------
if __name__ == "__main__":
    if not INFILE.exists():
        raise SystemExit("report.json not found. Run engine.py first.")
    with INFILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    build_pdf(data)
