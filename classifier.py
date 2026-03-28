from groq import Groq
import os
from dotenv import load_dotenv
load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def classify_goal(goal: str) -> tuple[str, list[str]]:
    """
    Dynamically classifies the goal and returns relevant diagnostic fields.
    No hardcoded categories — the model decides what's relevant.
    Returns: (archetype_label, [list of diagnostic field keys])
    """
    prompt = f"""You are a goal analysis assistant.

Given this goal: "{goal}"

1. Identify a SHORT category label for it (1-2 words, e.g. "language learning", "fitness", "career switch", "mental health", "creative skill", "financial", etc.)
2. List 4-6 short diagnostic field keys that would help personalize a plan for this goal. These should be snake_case strings like "current_level", "available_time", "deadline", "main_obstacle", etc.

Respond ONLY with valid JSON in this exact format, no explanation:
{{
  "archetype": "category label here",
  "fields": ["field_one", "field_two", "field_three", "field_four"]
}}"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=200
    )

    from core import safe_json
    result = safe_json(response.choices[0].message.content)
    return result["archetype"], result["fields"]