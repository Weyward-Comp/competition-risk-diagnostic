# app.py — Streamlit web app for the Competition Risk Diagnostic

import json, streamlit as st
from datetime import datetime
from pathlib import Path
import importlib.util, sys

st.set_page_config(page_title="Competition Risk Diagnostic", page_icon="🧭", layout="wide")

# Optional access code (set in Streamlit → Settings → Secrets)
if st.secrets.get("ACCESS_CODE"):
    code = st.text_input("Enter access code", type="password")
    if code != st.secrets["ACCESS_CODE"]:
        st.stop()

# Load engine helpers from local engine.py
spec = importlib.util.spec_from_file_location("engine_core", Path("engine.py"))
engine = importlib.util.module_from_spec(spec); sys.modules["engine_core"] = engine; spec.loader.exec_module(engine)

st.markdown("<style>.stRadio [role=radiogroup] label{font-weight:500}</style>", unsafe_allow_html=True)
st.title("Competition Risk Diagnostic")
st.caption("Answer neutral questions. Download your PDF dashboard and an editable Word report.")

# ---- init state
if "init" not in st.session_state:
    st.session_state.init = True
    st.session_state.rules = engine.load_rules("rules.yaml")
    engine.validate_rules_quick(st.session_state.rules)
    st.session_state.by_id = {b["id"]: b for b in st.session_state.rules}
    st.session_state.order = [b["id"] for b in st.session_state.rules]
    st.session_state.answers = {}
    st.session_state.items_by_domain = {}
    st.session_state.domain_scores = {}
    st.session_state.asked = set()
    st.session_state.current_id = "entityType"
    st.session_state.entity_type = None
    st.session_state.org = ""
    st.session_state.who = ""

_rerun = getattr(st, "rerun", getattr(st, "experimental_rerun", None))

def _record_item(qid, domain, question, answer, points, meta=None):
    it = {"id": qid, "domain": domain, "question": question, "answer": answer, "points": int(points)}
    meta = meta or {}
    for k in ("next_step", "risk_comment", "legal_basis", "action_priority", "tag", "hardcore"):
        if k in meta:
            it[k] = meta[k]
    st.session_state.items_by_domain.setdefault(domain, []).append(it)

def _next_question(block):
    nxt = engine.next_via_routes(block, st.session_state.answers, st.session_state.entity_type or "")
    if nxt and nxt not in st.session_state.asked:
        st.session_state.current_id = nxt
        if _rerun: _rerun(); return
    st.session_state.current_id = None
    if st.session_state.entity_type:
        for bid in st.session_state.order:
            if bid in st.session_state.asked: 
                continue
            b = st.session_state.by_id[bid]
            if engine.applies_to(b, st.session_state.entity_type) and engine.is_visible(b, st.session_state.answers, st.session_state.entity_type):
                st.session_state.current_id = bid
                if _rerun: _rerun(); return

def _build_payload():
    domains = []
    for name, sc in st.session_state.domain_scores.items():
        items = st.session_state.items_by_domain.get(name, [])
        risk, reason = engine.risk_from_score_and_items(int(sc), items)
        domains.append({
            "name": name,
            "score": int(sc),
            "risk": risk,
            "risk_override": reason,
            "items": items,
            "rationale": [],
            "next_steps": [],
        })
    all_items = [it for lst in st.session_state.items_by_domain.values() for it in lst]
    top_items = sorted([it for it in all_items if it["points"] > 0], key=lambda x: x["points"], reverse=True)[:5]
    return {
        "organisation": st.session_state.org,
        "completed_by": st.session_state.who,
        "entity_type": st.session_state.entity_type,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "rulebook_version": "rules.yaml",
        "overall_risk": engine.risk_bucket(int(sum(st.session_state.domain_scores.values()))),
        "total_score": int(sum(st.session_state.domain_scores.values())),
        "domains": domains,
        "top_items": top_items,
        "answers": {(st.session_state.by_id[q]["question"] if q in st.session_state.by_id else q): a 
                    for q,a in st.session_state.answers.items()},
        "executive_summary": "",
        "recommendations": [],
    }

# ---- sidebar
with st.sidebar:
    st.header("Report details")
    st.session_state.org = st.text_input("Organisation name", st.session_state.org)
    st.session_state.who = st.text_input("Completed by (name/role)", st.session_state.who)
    st.caption("Your answers live only in this session. Download files before closing the tab.")

# ---- questionnaire
if st.session_state.current_id:
    q = st.session_state.by_id[st.session_state.current_id]
    dom = q.get("domain", "General")
    kind = (q.get("kind") or "singleSelect").strip()
    opts = q.get("options", []) or []

    st.subheader(dom)
    st.write(f"**{q.get('question','')}**")

    with st.form(f"form_{q['id']}", clear_on_submit=False):
        if kind == "multiSelect":
            labels = [o["text"] for o in opts]
            selected = st.multiselect("Select all that apply", labels)
            submitted = st.form_submit_button("Next")
            if submitted:
                st.session_state.answers[q["id"]] = selected
                pts = 0
                for s in selected:
                    o = next((x for x in opts if x["text"] == s), None) or {}
                    p = int(o.get("points", 0)); pts += p
                    _record_item(q["id"], dom, q["question"], s, p, o)
                st.session_state.domain_scores[dom] = st.session_state.domain_scores.get(dom, 0) + pts
                st.session_state.asked.add(q["id"])
                _next_question(q)

        elif kind == "text":
            val = st.text_input("Your answer")
            submitted = st.form_submit_button("Next")
            if submitted:
                st.session_state.answers[q["id"]] = val
                _record_item(q["id"], dom, q["question"], val, 0, {})
                st.session_state.asked.add(q["id"])
                _next_question(q)

        else:
            labels = [o["text"] for o in opts] if opts else []
            val = st.radio("Choose one", labels if labels else ["(Type a free text answer below)"], index=0)
            freetext = st.text_input("Your answer") if not labels else ""
            submitted = st.form_submit_button("Next")
            if submitted:
                ans_text = freetext if not labels else val
                st.session_state.answers[q["id"]] = ans_text
                o = next((x for x in opts if x.get("text") == val), {}) if labels else {}
                p = 0 if not labels else int(o.get("points", 0))
                st.session_state.domain_scores[dom] = st.session_state.domain_scores.get(dom, 0) + p
                if q["id"] == "entityType":
                    st.session_state.entity_type = ans_text
                _record_item(q["id"], dom, q["question"], ans_text, p, o)
                st.session_state.asked.add(q["id"])
                _next_question(q)

    st.progress(min(1.0, len(st.session_state.asked) / max(1, len(st.session_state.order))))

else:
    st.success("All done — download your reports below.")
    data = _build_payload()
    import pdf_builder as pdfb
    import docx_builder as docxb
    c1, c2, c3 = st.columns([1,1,1])
    with c1:
        st.download_button("⬇️ Download PDF dashboard", data=pdfb.build_pdf_bytes(data),
                           file_name="report.pdf", mime="application/pdf")
    with c2:
        st.download_button("⬇️ Download Word report", data=docxb.build_docx_bytes(data),
                           file_name="report.docx",
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    with c3:
        st.download_button("⬇️ Download JSON (debug)", data=json.dumps(data, indent=2),
                           file_name="report.json", mime="application/json")
    if st.button("Start another response"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        if _rerun: _rerun()
