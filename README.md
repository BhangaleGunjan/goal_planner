# AI Goal Planner

Turn vague goals into structured, personalized action plans — powered by Groq (free).

## Setup

### 1. Get your free Groq API key
- Go to https://console.groq.com
- Sign up (free, no card needed)
- Create an API key

### 2. Set your API key
Create a `.env` file in the project root:
```
GROQ_API_KEY=your_key_here
```

Or set it as an environment variable:
```bash
export GROQ_API_KEY=your_key_here
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the app
```bash
uvicorn api:app --reload
```

Then open http://localhost:8000 in your browser.

### 5. (Optional) Test via CLI
```bash
python main.py
```

## File Structure
```
├── api.py          — FastAPI backend
├── engine.py       — Core LLM logic (Groq)
├── classifier.py   — Dynamic goal classification
├── core.py         — Utilities, validation, error handling
├── main.py         — CLI for testing
├── prompts/        — Prompt templates
│   ├── questions.txt
│   ├── plan.txt
│   └── ritual.txt
├── web/
│   └── index.html  — Frontend
└── requirements.txt
```
