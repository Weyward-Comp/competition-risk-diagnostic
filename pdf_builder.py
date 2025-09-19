# pdf_builder.py — dashboard + action sections (ReportLab + Matplotlib)
import io, textwrap
from typing import List, Dict
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def _wrap(s, width=22): return "\n".join(textwrap.wrap(str(s), width=width)) if s else ""
def _save_fig(fig, dpi=200):
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight"); plt.close(fig); buf.seek(0); return buf
def _rl_image(buf, max_w_mm, max_h_mm, dpi=200):
    buf.seek(0); im = PILImage.open(buf); w_px,h_px = im.size
    w_pt,h_pt = (w_px*72/dpi, h_px*72/dpi); mw, mh = (max_w_mm*mm, max_h_mm*mm)
    scale = min(mw/w_pt, mh/h_pt, 1.0); return Image(buf, width=w_pt*scale, height=h_pt*scale)
def _risk_color(r): return {"LOW": colors.HexColor("#43a047"), "MEDIUM": colors.HexColor("#fb8c00"), "HIGH": colors.HexColor("#e53935")}.get(r, colors.black)
def _mpl_risk(r):  return {"LOW":"#43a047","MEDIUM":"#fb8c00","HIGH":"#e53935"}.get(r,"#333333")

# charts (bounded height)
def _chart_domain_scores(domains):
    names=[d["name"] for d in domains] or ["—"]; scores=[int(d["score"]) for d in domains] or [0]
    h=min(4.8,max(2.2,0.32*len(names))); fig,ax=plt.subplots(figsize=(8,h),constrained_layout=True)
    y=range(len(names)); ax.barh(y,scores); ax.set_yticks(y); ax.set_yticklabels([_wrap(n,24) for n in names])
    ax.invert_yaxis(); ax.set_xlabel("Score"); ax.set_xlim(left=0); ax.grid(axis="x",linestyle=":",alpha=0.4)
    if scores: m=max(scores) or 1; [ax.text(v+m*0.02,i,str(v),va="center",fontsize=8) for i,v in enumerate(scores)]
    ax.set_title("Domain scores"); return _save_fig(fig)

def _chart_risk_heat(domains):
    names=[d["name"] for d in domains] or ["—"]; risks=[d["risk"] for d in domains] or ["LOW"]
    h=min(4.8,max(2.2,0.32*len(names))); fig,ax=plt.subplots(figsize=(8,h),constrained_layout=True)
    y=range(len(names)); ax.barh(y,[1]*len(names),color=[_mpl_risk(r) for r in risks])
    ax.set_yticks(y); ax.set_yticklabels([_wrap(n,24) for n in names]); ax.invert_yaxis()
    ax.set_xlabel("Risk bucket"); ax.set_xlim(0,1); ax.set_xticks([])
    [ax.text(0.02,i,r,va="center",ha="left",color="white" if r!="LOW" else "black",fontweight="bold",fontsize=8) for i,r in enumerate(risks)]
    ax.set_title("Risk buckets"); return _save_fig(fig)

def _chart_top_items(items):
    if not items:
        fig,ax=plt.subplots(figsize=(8,2.2),constrained_layout=True); ax.text(0.5,0.5,"No high-scoring items",ha="center",va="center"); ax.axis("off"); return _save_fig(fig)
    labels=[_wrap(f'{it.get("domain","")}: {it.get("answer","")}',32) for it in items]; vals=[int(it.get("points",0)) for it in items]
    h=min(4.5,max(2.2,0.36*len(labels))); fig,ax=plt.subplots(figsize=(8,h),constrained_layout=True)
    y=range(len(labels)); ax.barh(y,vals); ax.set_yticks(y); ax.set_yticklabels(labels); ax.invert_yaxis()
    ax.set_xlabel("Points"); ax.grid(axis="x",linestyle=":",alpha=0.4); m=max(vals) or 1
    [ax.text(v+m*0.02,i,str(v),va="center",fontsize=8) for i,v in enumerate(vals)]; ax.set_title("Top items"); return _save_fig(fig)

# action helpers
def _domain_items(dom: Dict): return list(dom.get("items") or [])
def _issue_text(it: Dict) -> str:
    if it.get("risk_comment"): return str(it["risk_comment"])
    q = str(it.get("question","")).strip(); a = str(it.get("answer","")).strip()
    return f"{q} — Answer: {a}" if q and a else (q or a or "Issue")
def _step_text(it: Dict) -> str: return it.get("next_step") or "Add recommended action…"
def _legal_text(it: Dict) -> str:
    if it.get("legal_basis"): return f"Legal notes: {it['legal_basis']}"
    cases = it.get("cases") or it.get("case_law") or []
    return ("Relevant case law: " + "; ".join(map(str, cases))) if cases else "Relevant case law: (to be added)"

def _action_table(items, small_style):
    rows = [["Issue", "Recommended next step", "Owner / notes"]]
    if not items:
        rows.append(["Review this domain — high aggregate risk.", "Identify and prioritise corrective actions.", ""])
    else:
        for it in items:
            rows.append([_issue_text(it), _step_text(it), ""])
    t = Table(rows, colWidths=[150*mm, 90*mm, 30*mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#eef2ff")),
        ("GRID",(0,0),(-1,-1),0.25, colors.HexColor("#c7c9d3")),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),4), ("RIGHTPADDING",(0,0),(-1,-1),4),
    ]))
    parts = [t, Spacer(1,3)]
    if items:
        parts += [Paragraph(_legal_text(items[0]), small_style), Spacer(1,8)]
    else:
        parts += [Spacer(1,8)]
    return parts

def build_pdf_bytes(data: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=14*mm, rightMargin=14*mm, topMargin=12*mm, bottomMargin=12*mm)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=20, spaceAfter=8)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=14, spaceBefore=6, spaceAfter=6)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10, leading=13)
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=9, textColor=colors.grey)

    story = [
        Paragraph(data.get("organisation","Report"), h1),
        Paragraph("Antitrust / Competition Risk Dashboard", h2),
        Paragraph(f'Completed by: {data.get("completed_by","")} — Generated: {data.get("generated_at","")}', small),
        Spacer(1,6)
    ]

    overall = data.get("overall_risk","LOW"); total = int(data.get("total_score",0))
    meta = Table([[Paragraph(f'<b>Overall risk:</b> <font color="{_risk_color(overall).hexval()}">{overall}</font>', body),
                   Paragraph(f"<b>Total score:</b> {total}", body)]], colWidths=[120*mm, 60*mm])
    meta.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.grey),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                              ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6)]))
    story += [meta, Spacer(1,8)]

    domains = data.get("domains", [])
    story += [_rl_image(_chart_risk_heat(domains), 270, 85), Spacer(1,6)]
    story += [_rl_image(_chart_domain_scores(domains), 270, 95), Spacer(1,6)]
    story += [Paragraph("Top items", h2), _rl_image(_chart_top_items(data.get("top_items", [])), 270, 95), Spacer(1,10)]

    # Action sections
    highs = [d for d in domains if d.get("risk") == "HIGH"]
    meds  = [d for d in domains if d.get("risk") == "MEDIUM"]

    story += [PageBreak(), Paragraph("Immediate actions (HIGH risk)", h2)]
    if not highs:
        story += [Paragraph("No domains scored HIGH. Review medium-risk areas below.", body), Spacer(1,6)]
    for d in highs:
        story += [Paragraph(d["name"], ParagraphStyle("domH", parent=h2, textColor=_risk_color("HIGH")))]
        story += _action_table(_domain_items(d), small)

    story += [Paragraph("Advice recommended (MEDIUM risk)", h2)]
    if not meds:
        story += [Paragraph("No domains scored MEDIUM.", body), Spacer(1,6)]
    for d in meds:
        story += [Paragraph(d["name"], ParagraphStyle("domM", parent=h2, textColor=_risk_color("MEDIUM")))]
        story += _action_table(_domain_items(d), small)

    # Per-domain details
    story += [PageBreak(), Paragraph("Per-domain details", h2)]
    for d in domains:
        story.append(Paragraph(f'{d["name"]} — {d.get("risk","")}',
                               ParagraphStyle("domAny", parent=h2, textColor=_risk_color(d.get("risk","LOW")))))
        items = d.get("items", [])
        rows = [["Question", "Answer", "Points"]]
        for it in items:
            rows.append([_wrap(it.get("question",""),80), _wrap(it.get("answer",""),45), str(int(it.get("points",0)))])
        tbl = Table(rows, colWidths=[160*mm, 90*mm, 20*mm], repeatRows=1)
        tbl.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0), colors.HexColor("#f0f0f0")),
                                 ("GRID",(0,0),(-1,-1), 0.25, colors.HexColor("#cccccc")),
                                 ("VALIGN",(0,0),(-1,-1), "TOP"),
                                 ("LEFTPADDING",(0,0),(-1,-1),4), ("RIGHTPADDING",(0,0),(-1,-1),4)]))
        story += [tbl, Spacer(1,6)]

    doc.build(story)
    buf.seek(0)
    return buf.read()
