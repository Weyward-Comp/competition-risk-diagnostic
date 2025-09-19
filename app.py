# app.py — Streamlit web app for the Competition Risk Diagnostic
# Put this file in the repo root with: engine.py, rules.yaml, pdf_builder.py, docx_builder.py

import json, streamlit as st
from datetime import datetime
from pathlib import Path
import importlib.util, sys

# -------- Optional access code (set ACCESS_CODE in Streamlit Secrets to enable) --------
if st.secrets.get("ACCESS_CODE"):
    st.set_page_config(page_title="Competition Risk Diagnostic", page_icon="🧭", layout="wide")
    st.title("Competition Risk Diagnostic")
    code = st.text_input("Enter access code", type="password")
    if code != st.secrets["ACCESS_CODE"]:
        st.stop()

# -------- Load engine helpers from local engine.py --------
spec = importlib.util.spec_from_file_location("engine_core", Path("engine.py"))
engine = importlib.util.module_from_spec(spec)
sys.modules["engine_core"] = engine
spec.loader.exec_module(engine)

# -------- Page settings / light CSS --------
st.set_page_config(page_title="Competition Risk Diagnostic", page_icon="🧭", layout="wide")
st.markdown("""<style>.stRadio [role=radiogroup] label{font-weight:500}</style>""", unsafe_allow_html=True)

st.title("Competition Risk Diagnostic")
st.caption("Answer a short set of neutral questions. Download your PDF dashboard and editable Word report at the end.")

# -------- Init state --------
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

# helper to support older/newer Streamlit
_rerun = getattr(st, "rerun", getattr(st, "experimental_rerun", None))

# -------- Small helpers --------
def _record_item(qid, domain, question, answer, points):
    it = {"id": qid, "domain": domain, "question": question, "answer": answer, "points": int(points)}
    st.session_state.items_by_domain.setdefault(domain, []).append(it)

def _next_question(block):
    """Go to routed 'next' if any, otherwise the next eligible block for the chosen entity."""
    nxt = engine.next_via_routes(block, st.session_state.answers, st.session_state.entity_type or "")
    if nxt and nxt not in st.session_state.asked:
        st.session_state.current_id = nxt
        if _rerun: _rerun()
        return
    st.session_state.current_id = None
    if st.session_state.entity_type:
        for bid in st.session_state.order:
            if bid in st.session_state.asked:
                continue
            b = st.session_state.by_id[bid]
            if engine.applies_to(b, st.session_state.entity_type) and engine.is_visible(b, st.session_state.answers, st.session_state.entity_type):
                st.session_state.current_id = bid
                if _rerun: _rerun()
                return

def _build_payload():
    domains = []
    for name, sc in st.session_state.domain_scores.items():
        domains.append({
            "name": name,
            "score": int(sc),
            "risk": engine.risk_bucket(int(sc)),
            "items": st.session_state.items_by_domain.get(name, []),
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
                    for q, a in st.session_state.answers.items()},
        "executive_summary": "",
        "recommendations": [],
    }

# -------- Sidebar (report details) --------
with st.sidebar:
    st.header("Report details")
    st.session_state.org = st.text_input("Organisation name", st.session_state.org)
    st.session_state.who = st.text_input("Completed by (name/role)", st.session_state.who)
    st.caption("Your answers live only in this session. Download files before closing the tab.")

# -------- Main flow --------
if st.session_state.current_id:
    block = st.session_state.by_id[st.session_state.current_id]
    dom = block.get("domain", "General")
    kind = (block.get("kind") or "singleSelect").strip()
    opts = block.get("options", []) or []

    st.subheader(dom)
    st.write(f"**{block.get('question','')}**")

    with st.form(f"form_{block['id']}", clear_on_submit=False):
        if kind == "multiSelect":
            labels = [o["text"] for o in opts]
            selected = st.multiselect("Select all that apply", labels)
            submitted = st.form_submit_button("Next")
            if submitted:
                st.session_state.answers[block["id"]] = selected
                pts = sum(next((int(o.get("points", 0)) for o in opts if o["text"] == s), 0) for s in selected)
                st.session_state.domain_scores[dom] = st.session_state.domain_scores.get(dom, 0) + pts
                for s in selected:
                    p = next((int(o.get("points", 0)) for o in opts if o["text"] == s), 0)
                    _record_item(block["id"], dom, block["question"], s, p)
                st.session_state.asked.add(block["id"])
                _next_question(block)

        elif kind == "text":
            val = st.text_input("Your answer")
            submitted = st.form_submit_button("Next")
            if sub
