# docx_builder.py — returns DOCX bytes (python-docx)
import io
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

def build_docx_bytes(data: dict) -> bytes:
    doc = Document()

    # Cover
    title = doc.add_paragraph()
    r = title.add_run(data.get("organisation","Report")); r.font.size = Pt(22); r.bold = True
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    doc.add_paragraph(f'Completed by: {data.get("completed_by","")}')
    doc.add_paragraph(f'Generated: {data.get("generated_at","")}')
    doc.add_paragraph(f'Overall risk: {data.get("overall_risk","")}'); doc.add_paragraph()

    # Domain summary
    doc.add_heading("Domain summary", level=1)
    tbl = doc.add_table(rows=1, cols=3)
    hdr = tbl.rows[0].cells; hdr[0].text, hdr[1].text, hdr[2].text = "Domain", "Score", "Risk"
    for d in data.get("domains", []):
        row = tbl.add_row().cells
        row[0].text, row[1].text, row[2].text = d["name"], str(int(d["score"])), d.get("risk","")
    doc.add_paragraph()

    # Top items
    doc.add_heading("Top items", level=1)
    if data.get("top_items"):
        t2 = doc.add_table(rows=1, cols=3)
        t2.rows[0].cells[0].text, t2.rows[0].cells[1].text, t2.rows[0].cells[2].text = "Domain", "Answer", "Points"
        for it in data["top_items"]:
            r = t2.add_row().cells
            r[0].text, r[1].text, r[2].text = it.get("domain",""), str(it.get("answer","")), str(int(it.get("points",0)))
    else:
        doc.add_paragraph("—")

    # Per-domain details
    doc.add_page_break()
    doc.add_heading("Per-domain details", level=1)
    for d in data.get("domains", []):
        doc.add_heading(f'{d["name"]} — {d.get("risk","")}', level=2)
        items = d.get("items", [])
        if not items:
            doc.add_paragraph("—"); continue
        t = doc.add_table(rows=1, cols=3)
        t.rows[0].cells[0].text, t.rows[0].cells[1].text, t.rows[0].cells[2].text = "Question", "Answer", "Points"
        for it in items:
            r = t.add_row().cells
            r[0].text, r[1].text, r[2].text = it.get("question",""), str(it.get("answer","")), str(int(it.get("points",0)))
        doc.add_paragraph()

    # Appendix
    doc.add_page_break()
    doc.add_heading("Appendix: Full Q&A", level=1)
    for q, a in data.get("answers", {}).items():
        p = doc.add_paragraph(); p.add_run(q + " ").bold = True
        p.add_run("→ " + (", ".join(a) if isinstance(a, list) else str(a)))

    out = io.BytesIO(); doc.save(out); out.seek(0); return out.read()
