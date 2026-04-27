# PawPal+ (Agentic AI Edition)

PawPal+ is a pet-care planner that now includes an **integrated AI copilot** inside the main app flow.

The project combines:
- deterministic task scheduling (priority, recurring tasks, conflicts)
- **agentic AI workflow** (plan -> act -> self-check)
- **retrieval-augmented generation (RAG)** over a local pet-care knowledge base
- guardrails + logging for safer and traceable behavior

## Advanced AI Features Included

### 1) Agentic Workflow (Integrated)
The AI assistant runs a multi-step loop every time it answers:
1. **Plan**: retrieve relevant notes + summarize schedule context
2. **Act**: generate a grounded recommendation (OpenAI model if key exists, local fallback otherwise)
3. **Check**: self-review output for citation/safety issues and revise if needed

This is integrated into:
- `app.py` -> **Today's Schedule** tab (AI Daily Briefing)
- `app.py` -> **AI Copilot** tab (custom Q&A)
- `main.py` -> CLI demo sections for agentic AI output

### 2) Retrieval-Augmented Generation (RAG)
The assistant retrieves top-matching chunks from:
- `assets/pet_care_knowledge.md`

The retrieved content is used directly to ground answers, and source titles are shown in output.

## Safety, Guardrails, and Logging

### Guardrails
Implemented in `ai_assistant.py`:
- blocks prompt-injection style requests (for example, "reveal system prompt")
- emergency keyword detection with immediate escalation messaging
- post-generation self-check for missing citations and unsafe medication phrasing

### Logging
AI events are logged to:
- `logs/pawpal_ai.log`

Logged events include retrieval metadata, guardrail triggers, and model/fallback mode.

## Project Structure

```
.
├── app.py                       # Streamlit app (main UI)
├── ai_assistant.py              # Agentic RAG assistant + guardrails + logging
├── pawpal_system.py             # Core OOP scheduler logic
├── main.py                      # CLI demo (including AI workflow)
├── assets/
│   └── pet_care_knowledge.md    # Retrieval knowledge base
├── tests/
│   ├── test_pawpal.py           # Core scheduler tests
│   └── test_ai_assistant.py     # AI reliability/guardrail tests
└── requirements.txt
```

## Reproducible Setup

### Prerequisites
- Python 3.10+
- `pip`

### 1) Install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Optional: enable live LLM generation
If you want OpenAI-backed generation (instead of local fallback), set:
```bash
export OPENAI_API_KEY="your_key_here"
```

If `OPENAI_API_KEY` is not set, the app still works in deterministic local RAG fallback mode.

### 3) Run the Streamlit app
```bash
streamlit run app.py
```

### 4) Run CLI demo
```bash
python3 main.py
```

### 5) Run tests
```bash
python3 -m pytest -q
```

Current result: **32 passing tests**.

## How to Verify AI Integration Quickly

1. Open **Today's Schedule** and generate a schedule.
2. Click **Generate AI briefing**.
3. Confirm you see:
   - AI response text
   - source list
   - agentic workflow trace
4. Open **AI Copilot** and ask a question.
5. Try a prompt-injection string and confirm guardrail blocking behavior.

## Notes
- The scheduler remains deterministic and testable.
- AI is additive and integrated into main behavior, not a standalone script.
- The system is designed to degrade gracefully when LLM access is unavailable.
