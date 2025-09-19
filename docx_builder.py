# docx_builder.py — action-oriented DOCX (returns bytes)
import io
from typing import List, Dict
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

def _shade(cell, hexcolor: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd'); shd.set(qn('w:fill'), hexcolor); tc_pr.append(shd)

def _risk_colors(risk: str):
    m = {"HIGH":("FDECEA","D93025"), "MEDIUM":("FFF4E5","B93815"), "LOW":("E8F5E9","1E7D32")}
    return m.get(risk, ("F3F4F6","111827"))

def _issue_text(it: Dict) -> str:
    if it.get("risk_comment"): return str(it["risk_comment"])
    q = str(it.get("question","")).strip(); a = str(it.get("answer","")).strip()
    return f"{q}  —  Answer: {a}" if q and a else (q or a or "Issue")

def _next_step_text(it: Dict) -> str:
    why = it.get("risk_comment") or ""
    base = it.get("next_step") or "Add recommended action…"
    return f"{base}" + (f" — Why: {why}" if why else "")

def _legal_text(it: Dict) -> str:
    if it.get("legal_basis"): return f"Legal notes: {it['legal_basis']}"
    cases = it.get("cases") or it.get("case_law") or []
    return ("Relevant case law: " + "; ".join(map(str, cases))) if cases else "Relevant case law: (to be added)"

def build_docx_bytes(data: dict) -> bytes:
    doc = Document()

    # Cover
    p = doc.add_paragraph(); r = p.add_run(data.get("organisation","Competition Risk Diagnostic"))
    r.font.size = Pt(22); r.bold = True; p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    doc.add_paragraph(f'Completed by: {data.get("completed_by","")}')
    doc.add_paragraph(f'Generated: {data.get("generated_at","")}')
    doc.add_paragraph(f'Overall risk: {data.get("overall_risk","")}'); doc.add_paragraph()

    # Domain summary
    doc.add_heading("Domain summary", level=1)
    tbl = doc.add_table(rows=1, cols=3); hdr = tbl.rows[0].cells
    hdr[0].text, hdr[1].text, hdr[2].text = "Domain", "Score", "Risk"
    highs, meds = [], []
    for d in data.get("domains", []):
        row = tbl.add_row().cells
        row[0].text, row[1].text, row[2].text = d["name"], str(int(d.get("score",0))), d.get("risk","")
        bg, _ = _risk_colors(d.get("risk","")); _shade(row[2], bg)
        if d.get("risk")=="HIGH": highs.append(d)
        elif d.get("risk")=="MEDIUM": meds.append(d)
    doc.add_paragraph()

    # Immediate actions
    doc.add_heading("Immediate actions (HIGH risk)", level=1)
    if not highs: doc.add_paragraph("No domains scored HIGH.")
    for d in highs:
        doc.add_heading(d["name"], level=2)
        t = doc.add_table(rows=1, cols=3)
        t.columns[0].width = Inches(3.6); t.columns[1].width = Inches(2.7); t.columns[2].width = Inches(1.6)
        h = t.rows[0].cells; h[0].text, h[1].text, h[2].text = "Issue", "Recommended next step", "Owner / notes"
        items = d.get("items", [])
        if not items:
            r = t.add_row().cells; r[0].text="High aggregate risk"; r[1].text="Identify corrective actions"; r[2].text=""
        else:
            for it in items:
                r = t.add_row().cells; r[0].text=_issue_text(it); r[1].text=_next_step_text(it); r[2].text=""
            doc.add_paragraph(_legal_text(items[0]))
        doc.add_paragraph()

    # Advice recommended
    doc.add_heading("Advice recommended (MEDIUM risk)", level=1)
    if not meds: doc.add_paragraph("No domains scored MEDIUM.")
    for d in meds:
        doc.add_heading(d["name"], level=2)
        t = doc.add_table(rows=1, cols=3)
        t.columns[0].width = Inches(3.6); t.columns[1].width = Inches(2.7); t.columns[2].width = Inches(1.6)
        h = t.rows[0].cells; h[0].text, h[1].text, h[2].text = "Topic / concern", "Why it matters / next step", "Owner / notes"
        items = d.get("items", [])
        if not items:
            r = t.add_row().cells; r[0].text="General review"; r[1].text="Obtain advice on grey areas"; r[2].text=""
        else:
            for it in items:
                r = t.add_row().cells; r[0].text=_issue_text(it); r[1].text=_next_step_text(it); r[2].text=""
        doc.add_paragraph()

    # Notes / additional explanation
    doc.add_heading("Additional explanation & follow-up notes", level=1)
    doc.add_paragraph("Use this section to add context, evidence, owners and dates for each domain.")
    for d in data.get("domains", []):
        doc.add_heading(d["name"], level=2)
        t = doc.add_table(rows=2, cols=3)
        t.columns[0].width = Inches(3.6); t.columns[1].width = Inches(2.3); t.columns[2].width = Inches(1.6)
        h = t.rows[0].cells; h[0].text, h[1].text, h[2].text = "Context / explanation", "Evidence / documents", "Owner / due date"
        r = t.rows[1].cells; r[0].text = r[1].text = r[2].text = ""
        doc.add_paragraph()

    out = io.BytesIO(); doc.save(out); out.seek(0); return out.read()
