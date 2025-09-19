# engine.py — rule loading, routing, and risk logic
# Used by app.py (Streamlit) to drive branching + risk.

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import yaml

# ----------------- load & validate -----------------
def load_rules(path: str | Path) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    if not isinstance(data, list):
        raise ValueError("rules.yaml must contain a top-level list of blocks.")
    return data

def validate_rules_quick(rules: List[Dict[str, Any]]) -> None:
    seen = set()
    for b in rules:
        if "id" not in b:
            raise ValueError("Every block needs an 'id'.")
        if b["id"] in seen:
            raise ValueError(f"Duplicate id in rules.yaml: {b['id']}")
        seen.add(b["id"])
        b.setdefault("domain", "General")
        # normalize fields we rely on
        if "appliesTo" in b and b["appliesTo"] is None:
            b.pop("appliesTo")
        if "options" in b and b["options"] is None:
            b["options"] = []
    # ok

# ----------------- visibility / routing -------------
def applies_to(block: Dict[str, Any], entity_type: str) -> bool:
    ats = block.get("appliesTo")
    return True if not ats else entity_type in ats

def _equals_condition(ans: Dict[str, Any], cond: Dict[str, Any]) -> bool:
    qid = cond.get("questionId")
    val = cond.get("value")
    if qid is None:
        return False
    a = ans.get(qid)
    if isinstance(a, list):
        return val in a
    return a == val

def is_visible(block: Dict[str, Any], answers: Dict[str, Any], entity_type: str) -> bool:
    if not applies_to(block, entity_type):
        return False
    vis = block.get("visibleIf")
    if not vis:
        return True
    # support: { equals: {questionId, value} }
    if "equals" in vis:
        return _equals_condition(answers, vis["equals"])
    return True

def next_via_routes(block: Dict[str, Any], answers: Dict[str, Any], entity_type: str) -> Optional[str]:
    """
    Routes defined as:
      next:
        - when: { equals: {questionId: <id>, value: "<text>"} }
          targetId: some_block
    Returns a targetId or None.
    """
    routes = block.get("next") or []
    for r in routes:
        w = r.get("when") or {}
        ok = True
        if "equals" in w:
            ok = _equals_condition(answers, w["equals"])
        if ok:
            return r.get("targetId")
    return None

# ----------------- risk logic -----------------------
def risk_bucket(score: int) -> str:
    if score >= 60:
        return "HIGH"
    if score >= 25:
        return "MEDIUM"
    return "LOW"

# any of these means cartel-level risk regardless of score
HARDCORE_TAGS = {"price_fixing", "market_sharing", "bid_rigging", "group_boycott"}

def risk_from_score_and_items(score: int, items: List[Dict[str, Any]]) -> Tuple[str, Optional[str]]:
    """
    HIGH if any item flagged hardcore (either item['hardcore'] True or tag in HARDCORE_TAGS).
    Else use thresholds.
    """
    for it in items or []:
        if it.get("hardcore") or (it.get("tag") in HARDCORE_TAGS):
            return "HIGH", f"Hardcore restriction detected ({it.get('tag','hardcore')})."
    return risk_bucket(score), None
