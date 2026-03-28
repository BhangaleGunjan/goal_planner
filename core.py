import json

# ===== PROMPT CACHE =====
# Prompts are loaded once at startup, not on every request

_prompt_cache = {}

def load_prompt(name):
    if name not in _prompt_cache:
        try:
            with open(f"prompts/{name}.txt") as f:
                _prompt_cache[name] = f.read()
        except FileNotFoundError:
            raise RuntimeError(f"Prompt file 'prompts/{name}.txt' not found.")
    return _prompt_cache[name]

# ===== SAFE JSON PARSING =====

def safe_json(text):
    """Attempt to extract and parse JSON from LLM output. Raises ValueError on failure."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON object
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        pass

    # Try to extract JSON array
    try:
        start = text.index("[")
        end = text.rindex("]") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        pass

    raise ValueError(f"Could not parse valid JSON from model response:\n{text[:300]}")

# ===== NORMALIZERS =====

def normalize_questions(qs):
    if not isinstance(qs, list):
        raise ValueError("Questions must be a list.")
    fixed = []
    for q in qs:
        if "question" in q and "maps_to" in q:
            fixed.append(q)
        else:
            text = q.get("text") or q.get("ask") or q.get("q")
            key = q.get("maps") or q.get("maps_to") or q.get("field")
            if text and key:
                fixed.append({"question": text, "maps_to": key})
    return fixed

def normalize_plan(plan):
    if not isinstance(plan, dict) or "phases" not in plan:
        raise ValueError("Plan must be a dict with a 'phases' key.")
    for p in plan.get("phases", []):
        for s in p.get("steps", []):
            if "effort" not in s:
                s["effort"] = "medium"
    return plan

def normalize_ritual(r):
    if isinstance(r, list):
        return {
            "DAILY_RITUAL": [str(x) for x in r],
            "WEEKLY_INTENSIFIER": "",
            "COMPLETION_SIGNALS": []
        }
    if isinstance(r, dict):
        return {
            "DAILY_RITUAL": [str(x) for x in r.get("DAILY_RITUAL", [])],
            "WEEKLY_INTENSIFIER": str(r.get("WEEKLY_INTENSIFIER", "")),
            "COMPLETION_SIGNALS": [str(x) for x in r.get("COMPLETION_SIGNALS", [])]
        }
    return {"DAILY_RITUAL": [], "WEEKLY_INTENSIFIER": "", "COMPLETION_SIGNALS": []}

# ===== INPUT VALIDATION =====

def validate_goal(goal: str):
    """Returns (is_valid, error_message)"""
    if not goal or not goal.strip():
        return False, "Goal cannot be empty."
    if len(goal.strip()) < 5:
        return False, "Goal is too short. Please describe what you want to achieve."
    if len(goal.strip()) > 300:
        return False, "Goal is too long. Please keep it under 300 characters."
    if not any(c.isalpha() for c in goal):
        return False, "Goal must contain actual words."
    return True, None
