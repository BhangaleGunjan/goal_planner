import json
import os
from groq import Groq
from core import safe_json, normalize_plan, normalize_questions, normalize_ritual, load_prompt
from classifier import classify_goal

MODEL = "llama-3.3-70b-versatile"

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def _chat(prompt: str, temperature: float = 0.7, max_tokens: int = 2048) -> str:
    """Single helper for all non-streaming Groq calls."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens
    )
    return response.choices[0].message.content

def start_session(goal: str) -> list:
    """Classify goal and generate diagnostic questions."""
    archetype, fields = classify_goal(goal)

    prompt = load_prompt("questions") \
        .replace("{{ARCHETYPE}}", archetype) \
        .replace("{{FIELDS}}", json.dumps(fields)) \
        .replace("{{GOAL}}", goal)

    raw = _chat(prompt, temperature=0.4, max_tokens=600)
    return normalize_questions(safe_json(raw))

def generate_plan(goal: str, profile: dict) -> dict:
    """Generate a full multi-phase plan with rituals."""
    prompt = load_prompt("plan") \
        .replace("{{GOAL}}", goal) \
        .replace("{{PROFILE}}", json.dumps(profile))

    raw = _chat(prompt, temperature=0.7, max_tokens=3000)
    plan = normalize_plan(safe_json(raw))

    for phase in plan["phases"]:
        try:
            ritual = _deepen_phase(phase)
            phase["daily_ritual"] = ritual["DAILY_RITUAL"]
            phase["weekly_intensifier"] = ritual["WEEKLY_INTENSIFIER"]
            phase["completion_signals"] = ritual["COMPLETION_SIGNALS"]
        except Exception as e:
            print(f"[deepen_phase error] {e}")
            phase["daily_ritual"] = []
            phase["weekly_intensifier"] = ""
            phase["completion_signals"] = []

    return plan

def generate_plan_stream(goal: str, profile: dict):
    """
    Streaming version of generate_plan.
    Yields server-sent event strings for real-time UI updates.
    """
    # Step 1: generate the raw plan
    prompt = load_prompt("plan") \
        .replace("{{GOAL}}", goal) \
        .replace("{{PROFILE}}", json.dumps(profile))

    yield f"data: {json.dumps({'type': 'status', 'message': 'Building your plan...'})}\n\n"

    try:
        stream = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=3000,
            stream=True
        )
        raw_plan = ""
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            raw_plan += delta
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Plan generation failed: {str(e)}'})}\n\n"
        return

    # Step 2: parse plan
    try:
        plan = normalize_plan(safe_json(raw_plan))
    except ValueError as e:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Could not parse plan: {str(e)}'})}\n\n"
        return

    # Step 3: deepen each phase with rituals
    total = len(plan["phases"])
    for i, phase in enumerate(plan["phases"]):
        yield f"data: {json.dumps({'type': 'status', 'message': f'Deepening phase {i+1} of {total}...'})}\n\n"
        try:
            ritual = _deepen_phase(phase)
            phase["daily_ritual"] = ritual["DAILY_RITUAL"]
            phase["weekly_intensifier"] = ritual["WEEKLY_INTENSIFIER"]
            phase["completion_signals"] = ritual["COMPLETION_SIGNALS"]
        except Exception as e:
            print(f"[deepen_phase stream error] {e}")
            phase["daily_ritual"] = []
            phase["weekly_intensifier"] = ""
            phase["completion_signals"] = []

    yield f"data: {json.dumps({'type': 'plan', 'data': plan})}\n\n"
    yield "data: [DONE]\n\n"

def _deepen_phase(phase: dict) -> dict:
    prompt = load_prompt("ritual").replace("{{PHASE}}", json.dumps(phase))
    raw = _chat(prompt, temperature=0.6, max_tokens=800)
    return normalize_ritual(safe_json(raw))

def adapt_plan(plan_data: dict, task_states: dict, going_well: str, difficult: str) -> dict:
    """
    Rewrites incomplete phases based on user feedback.
    task_states: dict like {"0-0": true, "0-1": false, ...}
    Returns the full updated plan_data with incomplete phases rewritten.
    """
    phases = plan_data["phases"]

    # Figure out which phases are fully completed
    first_incomplete = len(phases)  # default: all complete
    for pi, phase in enumerate(phases):
        phase_tasks = [task_states.get(f"{pi}-{ti}", False) for ti in range(len(phase["steps"]))]
        if not all(phase_tasks):
            first_incomplete = pi
            break

    if first_incomplete == len(phases):
        # All phases done, nothing to adapt
        return plan_data

    incomplete_phases = phases[first_incomplete:]
    completed_phases = phases[:first_incomplete]

    # Build a summary of completed tasks
    completed_summary = []
    for pi in range(first_incomplete):
        for ti, step in enumerate(phases[pi]["steps"]):
            if task_states.get(f"{pi}-{ti}", False):
                completed_summary.append(step["task"])

    prompt = load_prompt("adapt") \
        .replace("{{GOAL}}", plan_data.get("goal", "the user's goal")) \
        .replace("{{PHASES}}", json.dumps(incomplete_phases)) \
        .replace("{{COMPLETED}}", json.dumps(completed_summary)) \
        .replace("{{GOING_WELL}}", going_well or "Nothing specified") \
        .replace("{{DIFFICULT}}", difficult or "Nothing specified")

    raw = _chat(prompt, temperature=0.7, max_tokens=3000)
    new_incomplete = safe_json(raw)

    if not isinstance(new_incomplete, list):
        raise ValueError("Adapt prompt returned unexpected format.")

    # Deepen each new phase with rituals
    for phase in new_incomplete:
        try:
            ritual = _deepen_phase(phase)
            phase["daily_ritual"] = ritual["DAILY_RITUAL"]
            phase["weekly_intensifier"] = ritual["WEEKLY_INTENSIFIER"]
            phase["completion_signals"] = ritual["COMPLETION_SIGNALS"]
        except Exception as e:
            print(f"[adapt deepen error] {e}")
            phase["daily_ritual"] = []
            phase["weekly_intensifier"] = ""
            phase["completion_signals"] = []

    # Rebuild full plan
    updated_plan = dict(plan_data)
    updated_plan["phases"] = completed_phases + new_incomplete

    return updated_plan, first_incomplete