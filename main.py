from dotenv import load_dotenv
load_dotenv()
from core import validate_goal
from engine import start_session, generate_plan
import json

def main():
    print("=" * 50)
    print("  AI Goal Planner — CLI")
    print("=" * 50)

    goal = input("\nEnter your goal: ").strip()

    valid, error = validate_goal(goal)
    if not valid:
        print(f"\n[Error] {error}")
        return

    print("\nAnalyzing your goal...")
    try:
        qs = start_session(goal)
    except Exception as e:
        print(f"\n[Error] Could not generate questions: {e}")
        return

    profile = {}
    print("\nAnswer a few questions to personalize your plan:\n")
    for q in qs:
        answer = input(f"  {q['question']} ").strip()
        profile[q["maps_to"]] = answer

    print("\nGenerating your plan (this may take a moment)...")
    try:
        plan = generate_plan(goal, profile)
    except Exception as e:
        print(f"\n[Error] Could not generate plan: {e}")
        return

    print("\n" + "=" * 50)
    print(f"  PLAN: {goal.upper()}")
    print("=" * 50)

    for i, phase in enumerate(plan["phases"]):
        print(f"\n--- Phase {i+1}: {phase['name']} ---")
        for step in phase["steps"]:
            effort = {"low": "Easy", "medium": "Moderate", "high": "Hard"}.get(step["effort"], "Moderate")
            print(f"  • {step['task']}  [{effort}]")

        if phase.get("daily_ritual"):
            print("\n  Daily Ritual:")
            for r in phase["daily_ritual"]:
                print(f"    - {r}")

        if phase.get("completion_signals"):
            print("\n  Done when:")
            for c in phase["completion_signals"]:
                print(f"    ✓ {c}")

    print("\n" + "=" * 50)
    print("  Consistency beats intensity. Start today.")
    print("=" * 50 + "\n")

if __name__ == "__main__":
    main()
