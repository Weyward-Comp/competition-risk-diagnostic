# build_docx.py — DOCX with Immediate Action trigger (≥60 overall or any domain)
# Usage:
#   py -m pip install python-docx
#   py build_docx.py

import json
from pathlib import Path
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.shared import OxmlElement, qn

REPORT_JSON = Path("report.json")
OUTPUT_DOCX = Path("report.docx")

def load_report():
    if not REPORT_JSON.exists():
        raise FileNotFoundError("report.json not found. Run the questionnaire first.")
    with REPORT_JSON.open("r", encoding="utf-8") as f:
        return json.load(f)

def add_toc(doc):
    p = doc.add_paragraph()
    r = p.add_run()
    fld = OxmlElement('w:fldSimple')
    fld.set(qn('w:instr'), 'TOC \\o "1-3" \\h \\z \\u')
    r._r.append(fld)

def para(doc, text, bold=False, size=11):
    p = doc.add_paragraph(text)
    if p.runs:
        p.runs[0].bold = bold
        p.runs[0].font.size = Pt(size)
    return p

def badge(r):
    return {"HIGH":"HIGH","MEDIUM":"MEDIUM","LOW":"LOW"}.get(r, r or "")

def high_trigger(R):
    if R.get("total_score",0) >= 60:
        return True
    for d in R.get("domains", []):
        if d.get("score",0) >= 60:
            return True
    return False

def main():
    R = load_report()
    doc = Document()

    # Cover
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("Weyward Competition\nSports Governance & Commercialisation — Antitrust Triage")
    run.bold = True; run.font.size = Pt(18)

    tbl = doc.add_table(rows=0, cols=2)
    for k, v in [
        ("Organisation", R.get("organisation","—")),
        ("Completed by", R.get("completed_by","—")),
        ("Generated", R.get("generated_at","")),
        ("Rulebook", R.get("rulebook_version","")),
        ("Overall Risk", badge(R.get("overall_risk",""))),
        ("Total Score", str(R.get("total_score",0))),
    ]:
        row = tbl.add_row().cells
        row[0].text = k
        row[1].text = v

    if high_trigger(R):
        para(doc, "IMMEDIATE ACTION REQUIRED — High risk identified (≥ 60).", bold=True, size=12)

    doc.add_paragraph()
    para(doc, "Table of Contents", bold=True, size=14); add_toc(doc)
    doc.add_page_break()

    # Action sections
    high_items, med_items = [], []
    for d in R.get("domains", []):
        # item-level
        for it in d.get("items", []):
            if it.get("points",0) > 0:
                pr = (it.get("action_priority") or "").upper()
                item = {"domain": d["name"], **it}
                if pr == "HIGH": high_items.append(item)
                elif pr == "MEDIUM": med_items.append(item)
        # domain-level fallback
        if d.get("score",0) >= 60:
            high_items.append({"domain": d["name"], "answer": "(Domain score ≥60)", "question": "",
                               "risk_comment": "Domain score suggests significant competition risk exposure.",
                               "legal_basis": None, "next_step": "Escalate to counsel; implement short-term mitigations.",
                               "points": d.get("score",0)} )
        elif 25 <= d.get("score",0) <= 59:
            med_items.append({"domain": d["name"], "answer": "(Domain score 25–59)", "question": "",
                              "risk_comment": "Moderate risk requiring closer review.",
                              "legal_basis": None, "next_step": "Seek further legal advice; refine policies.",
                              "points": d.get("score",0)} )

    para(doc, "Immediate Action Required", bold=True, size=16)
    if not high_items:
        para(doc, "None identified by the questionnaire.")
    else:
        for it in sorted(high_items, key=lambda x: x.get("points",0), reverse=True):
            para(doc, f"{it['domain']}: {it['answer']} {('— ' + it['question']) if it.get('question') else ''}", bold=True)
            if it.get("risk_comment"): para(doc, f"Why this matters: {it['risk_comment']}")
            if it.get("legal_basis"):  para(doc, f"Legal basis: {it['legal_basis']}")
            if it.get("next_step"):    para(doc, f"Action: {it['next_step']}")
            doc.add_paragraph()

    doc.add_paragraph()
    para(doc, "Further Advice Recommended", bold=True, size=16)
    if not med_items:
        para(doc, "None identified.")
    else:
        for it in sorted(med_items, key=lambda x: x.get("points",0), reverse=True):
            para(doc, f"{it['domain']}: {it['answer']} {('— ' + it['question']) if it.get('question') else ''}", bold=True)
            if it.get("risk_comment"): para(doc, f"Why this matters: {it['risk_comment']}")
            if it.get("legal_basis"):  para(doc, f"Legal basis: {it['legal_basis']}")
            if it.get("next_step"):    para(doc, f"Suggested next step: {it['next_step']}")
            doc.add_paragraph()

    doc.add_page_break()

    # Domain analysis (editable)
    para(doc, "Domain Analysis", bold=True, size=16)
    for d in sorted(R.get("domains", []), key=lambda x: x["score"], reverse=True):
        para(doc, f"{d['name']} — {badge(d['risk'])} (Score {d['score']})", bold=True, size=14)
        positives = [it for it in d.get("items", []) if it.get("points",0) > 0]
        if not positives:
            para(doc, "No specific flagged items recorded by the tool.")
        else:
            for it in positives:
                para(doc, f"- {it['answer']} — {it['question']} (+{it['points']})")
                if it.get("risk_comment"): para(doc, f"   Why: {it['risk_comment']}")
                if it.get("legal_basis"):  para(doc, f"   Legal basis: {it['legal_basis']}")
                if it.get("next_step"):    para(doc, f"   Action: {it['next_step']}")
                doc.add_paragraph()
        para(doc, "Your analysis / notes:", bold=True)
        para(doc, "[Insert tailored explanation, case citations, and client-specific steps]")
        doc.add_paragraph()

    doc.add_page_break()
    # Q&A appendix
    para(doc, "Appendix — Full Questionnaire & Answers", bold=True, size=16)
    for q, a in R.get("answers", {}).items():
        para(doc, f"• {q}")
        para(doc, f"   Selected: {a}")

    doc.save(OUTPUT_DOCX)
    print(f"Created {OUTPUT_DOCX.resolve()}")

if __name__ == "__main__":
    main()
