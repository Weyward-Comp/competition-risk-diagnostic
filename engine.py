# engine.py — branching + items + report.json for PDF/DOCX
from __future__ import annotations
import json, yaml, re, sys
from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path

RULEBOOK_FILE = "rules.yaml"
REPORT_JSON = Path("report.json")

# ==============================
# Normalisation & defaults
# ==============================
def _slug(s: str) -> str:
    import re as _re
    s = _re.sub(r"\s+", "-", (s or "").strip())
    s = _re.sub(r"[^a-zA-Z0-9\-]", "", s)
    return (s.lower() or "q")[:40]

ENTITY_PICKER_BLOCK = {
    "id": "entityType",
    "domain": "Meta",
    "question": "Which best describes your organisation?",
    "kind": "singleSelect",
    "options": [
        {"text": "International Federation", "points": 0},
        {"text": "National Federation", "points": 0},
        {"text": "League Operator", "points": 0},
        {"text": "Club / Team", "points": 0},
        {"text": "Event Owner / Promoter", "points": 0},
        {"text": "Players' Union", "points": 0},
        {"text": "Athlete / Agent", "points": 0},
        {"text": "Refereeing Body", "points": 0},
        {"text": "Academy / Training Centre", "points": 0},
        {"text": "Venue / Stadium Operator", "points": 0},
        {"text": "Data / Analytics Provider", "points": 0},
        {"text": "Ticketing / Hospitality", "points": 0},
        {"text": "Betting / Integrity Partner", "points": 0},
        {"text": "Broadcast / Media / OTT", "points": 0},
        {"text": "Sponsorship / Marketing Agency", "points": 0},
        {"text": "Merchandising / Licensing", "points": 0},
        {"text": "Technology Platform", "points": 0},
        {"text": "Esports Organisation", "points": 0},
    ],
    "appliesTo": "all",
}

def load_rules(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    if not isinstance(raw, list):
        raise ValueError("rules.yaml must be a YAML list of question blocks.")
    return normalize_rules(raw)

def normalize_rules(raw_rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    norm: List[Dict[str, Any]] = []
    for i, b in enumerate(raw_rules, start=1):
        nb = dict(b or {})
        nb.setdefault("id", f"q{i:02d}_{_slug(nb.get('question',''))}")
        nb.setdefault("kind", "singleSelect")
        nb.setdefault("appliesTo", "all")
        nb["options"] = (nb.get("options", []) or [])  # ensure list, not None
        norm.append(nb)
    # Ensure entityType exists at the beginning
    if not any(b.get("id") == "entityType" for b in norm):
        norm = [ENTITY_PICKER_BLOCK] + norm
    return norm

def validate_rules_quick(rules: List[Dict[str, Any]]) -> None:
    errors: List[str] = []
    for idx, b in enumerate(rules, start=1):
        bid = b.get("id", f"<no-id-#{idx}>")
        if not b.get("question"):
            errors.append(f"{bid}: missing 'question'")
        if "appliesTo" not in b:
            errors.append(f"{bid}: missing 'appliesTo' (use 'all' or a list)")
        opts = b.get("options", [])
        if opts is None or not isinstance(opts, list):
            errors.append(f"{bid}: 'options' must be a list (use [] if none)")
        else:
            for j, opt in enumerate(opts, start=1):
                if not isinstance(opt, dict):
                    errors.append(f"{bid} option #{j}: option must be a dict")
                else:
                    if "text" not in opt:
                        errors.append(f"{bid} option #{j}: missing 'text'")
                    if "points" not in opt:
                        errors.append(f"{bid} option #{j}: missing 'points'")
    if errors:
        print("\nRule validation warnings:")
        for e in errors:
            print(" -", e)
        print()

# ==============================
# Predicate evaluation
# ==============================
def _json_eq(a: Any, b: Any) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

def eval_predicate(pred: Optional[Dict[str, Any]],
                   answers: Dict[str, Any],
                   entity_type: str) -> bool:
    if not pred:
        return True
    if "any" in pred:
        return any(eval_predicate(p, answers, entity_type) for p in (pred.get("any") or []))
    if "all" in pred:
        return all(eval_predicate(p, answers, entity_type) for p in (pred.get("all") or []))
    if "not" in pred:
        return not eval_predicate(pred.get("not"), answers, entity_type)
    if "equals" in pred:
        qid = pred["equals"]["questionId"]
        val = pred["equals"]["value"]
        return _json_eq(answers.get(qid), val)
    if "includes" in pred:
        qid = pred["includes"]["questionId"]
        val = pred["includes"]["value"]
        a = answers.get(qid)
        return isinstance(a, list) and val in a
    if "in" in pred:
        qid = pred["in"]["questionId"]
        vals = pred["in"]["values"]
        return any(_json_eq(answers.get(qid), v) for v in vals)
    if "entityIn" in pred:
        return entity_type in (pred["entityIn"].get("values") or [])
    return False

def applies_to(block: Dict[str, Any], entity_type: str) -> bool:
    ap = block.get("appliesTo", "all")
    return ap == "all" or (isinstance(ap, list) and entity_type in ap)

def is_visible(block: Dict[str, Any],
               answers: Dict[str, Any],
               entity_type: str) -> bool:
    return eval_predicate(block.get("showIf"), answers, entity_type)

def next_via_routes(block: Dict[str, Any],
                    answers: Dict[str, Any],
                    entity_type: str) -> Optional[str]:
    for rule in (block.get("next") or []):
        if eval_predicate(rule.get("when"), answers, entity_type):
            return rule.get("targetId")
    return None

# ==============================
# CLI helpers
# ==============================
def ask_single_select(prompt: str, options: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not options:
        # Open answer fallback for singleSelect with no options
        val = input(f"{prompt}\n> ").strip()
        return {"text": val, "points": 0}
    print(f"\n{prompt}")
    for i, opt in enumerate(options, start=1):
        print(f"  {i}. {opt.get('text')}")
    while True:
        raw = input("Choose an option number: ").strip()
        if raw.isdigit():
            k = int(raw)
            if 1 <= k <= len(options):
                return options[k - 1]
        print("Please enter a valid number.")

def ask_multi_select(prompt: str, options: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not options:
        print(f"\n{prompt}")
        input("Press Enter to continue (no predefined choices). ")
        return []
    print(f"\n{prompt}")
    for i, opt in enumerate(options, start=1):
        print(f"  {i}. {opt.get('text')}")
    print("Select numbers separated by commas (or leave blank for none).")
    raw = input("> ").strip()
    if not raw:
        return []
    chosen: List[Dict[str, Any]] = []
    parts = [p.strip() for p in raw.split(",") if p.strip().isdigit()]
    for p in parts:
        k = int(p)
        if 1 <= k <= len(options):
            chosen.append(options[k - 1])
    # de-duplicate
    seen = set()
    unique = []
    for c in chosen:
        key = c.get("text")
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique

# ==============================
# Risk bucketing (for report)
# ==============================
def risk_bucket(score: int) -> str:
    if score >= 60: return "HIGH"
    if score >= 25: return "MEDIUM"
    return "LOW"

def risk_flags(answers: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    if answers.get("setsParticipationRules") == "Yes" and answers.get("publishesCriteria") in (None, "No"):
        flags.append("Participation rules without published criteria")
    if answers.get("jointCommercialDecisions") == "Yes":
        if answers.get("leagueApprovalForJointSales") in (None, "No") or answers.get("fedApprovalForJointSales") in (None, "No"):
            flags.append("Joint selling without formal approval")
    if answers.get("exclusiveAgreements") == "Yes" and answers.get("exclusivityDetails") in (None, "No, not usually"):
        flags.append("Exclusive agreements without clear limits")
    if answers.get("leagueDataCollection") == "Yes" and answers.get("leagueAltDataAccess") in (None, "No"):
        flags.append("Limited venue data access without route for others")
    if answers.get("dataExclusivity") == "Yes" and answers.get("dataNonExclusivePathways") in (None, "No"):
        flags.append("Exclusive data supply without access pathway")
    if answers.get("ticketingExclusivePartner") == "Yes" and answers.get("ticketingResalePolicy") == "No":
        flags.append("Exclusive ticketing with no external resale")
    if answers.get("clubCoordinationOnPlayers") == "Yes":
        flags.append("Club-to-club coordination on players")
    return flags

# ==============================
# Orchestration
# ==============================
def run() -> None:
    print("Sports Antitrust Triage — Governance & Commercialisation")
    org = input("Organisation name (for the report cover): ").strip()
    who = input("Completed by (name/role): ").strip()

    rules = load_rules(RULEBOOK_FILE)
    validate_rules_quick(rules)

    by_id = {b["id"]: b for b in rules}
    order = [b["id"] for b in rules]

    answers: Dict[str, Any] = {}
    asked: set[str] = set()
    domain_scores: Dict[str, int] = {}
    # NEW: collect detailed items per domain and globally
    items_by_domain: Dict[str, List[Dict[str, Any]]] = {}
    all_items: List[Dict[str, Any]] = []

    # Start at entityType
    current_id: Optional[str] = "entityType"
    entity_type: Optional[str] = None

    while current_id:
        block = by_id[current_id]
        q = block.get("question", "<no question>")
        kind = (block.get("kind") or "singleSelect").strip()
        opts = block.get("options", []) or []
        domain = block.get("domain", "General")

        # Ask, score, and capture items
        if kind == "multiSelect":
            chosen_list = ask_multi_select(q, opts)
            answers[current_id] = [c.get("text") for c in chosen_list]
            points = sum(int(c.get("points", 0)) for c in chosen_list)

            # each selected option becomes its own item
            for c in chosen_list:
                item = {
                    "id": current_id,
                    "domain": domain,
                    "question": q,
                    "answer": c.get("text"),
                    "points": int(c.get("points", 0)),
                }
                # optional metadata on the option
                for k in ("next_step", "risk_comment", "legal_basis", "action_priority"):
                    if k in c:
                        item[k] = c[k]
                items_by_domain.setdefault(domain, []).append(item)
                all_items.append(item)

        elif kind == "text":
            val = input(f"\n{q}\n> ").strip()
            answers[current_id] = val
            points = 0
            # record as a neutral item (0 points)
            items_by_domain.setdefault(domain, []).append({
                "id": current_id, "domain": domain, "question": q, "answer": val, "points": 0
            })

        else:  # singleSelect (default)
            chosen = ask_single_select(q, opts)
            answers[current_id] = chosen.get("text")
            points = int(chosen.get("points", 0))

            item = {
                "id": current_id,
                "domain": domain,
                "question": q,
                "answer": chosen.get("text"),
                "points": points,
            }
            for k in ("next_step", "risk_comment", "legal_basis", "action_priority"):
                if k in chosen:
                    item[k] = chosen[k]
            items_by_domain.setdefault(domain, []).append(item)
            all_items.append(item)

        # capture entity
        if current_id == "entityType":
            entity_type = answers[current_id]

        # accumulate domain score
        domain_scores[domain] = domain_scores.get(domain, 0) + points
        asked.add(current_id)

        # explicit routing first
        nxt = next_via_routes(block, answers, entity_type or "")
        if nxt and nxt not in asked:
            current_id = nxt
            continue

        # otherwise fall through to next eligible in order
        current_id = None
        if entity_type:
            for bid in order:
                if bid in asked:
                    continue
                b = by_id[bid]
                if applies_to(b, entity_type) and is_visible(b, answers, entity_type):
                    current_id = bid
                    break

    # ---------------------------
    # Build report.json for PDF/DOCX
    # ---------------------------
    total_score = int(sum(domain_scores.values()))
    overall_risk = risk_bucket(total_score)

    # shape domains list with items
    domains_list: List[Dict[str, Any]] = []
    for d_name, sc in domain_scores.items():
        domains_list.append({
            "name": d_name,
            "score": int(sc),
            "risk": risk_bucket(int(sc)),
            "items": items_by_domain.get(d_name, []),
            "rationale": [],   # (optional) free text; add later if desired
            "next_steps": [],  # (optional) free text; add later if desired
        })

    # Top 5 highest-scoring items (positives only)
    top_items = sorted(
        [it for it in all_items if isinstance(it.get("points"), int) and it["points"] > 0],
        key=lambda x: x["points"],
        reverse=True
    )[:5]

    report = {
        "organisation": org,
        "completed_by": who,
        "entity_type": entity_type,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "rulebook_version": "rules.yaml",
        "overall_risk": overall_risk,
        "total_score": total_score,
        "domains": domains_list,
        "top_items": top_items,
        # Q&A appendix: question text -> selected answer(s)
        "answers": { (by_id[q]["question"] if q in by_id else q): a for q, a in answers.items() },
        # Optional narrative fields your DOCX builder can pick up:
        "executive_summary": "",
        "recommendations": [],
    }

    with REPORT_JSON.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # ---------------------------
    # Console summary
    # ---------------------------
    print("\n--- Summary ---")
    print(f"Organisation: {org}")
    print(f"Completed by: {who}")
    print(f"Entity type:  {entity_type}")
    print("\nDomain scores:")
    for d, sc in domain_scores.items():
        print(f" - {d}: {sc}")

    flags = risk_flags(answers)
    if flags:
        print("\nPotential attention points:")
        for f in flags:
            print(" •", f)

    print(f"\nSaved report → {REPORT_JSON.resolve()}")
    print("Now run:  python build_pdf.py   and   python build_docx.py")

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nExited.")
        sys.exit(1)
