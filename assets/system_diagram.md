# PawPal+ System Diagram

```mermaid
flowchart LR
  U[Human User] --> UI[Streamlit UI<br/>app.py]

  UI --> SCHED[Deterministic Scheduler<br/>pawpal_system.py]
  UI --> AGENT[AI Copilot (Agentic)<br/>ai_assistant.py]

  AGENT --> RETRIEVER[Retriever<br/>assets/pet_care_knowledge.md]
  SCHED --> CONTEXT[Schedule Context]
  RETRIEVER --> GENERATOR[Answer Generation<br/>LLM or Local Fallback]
  CONTEXT --> GENERATOR

  GENERATOR --> EVAL[Self-Check + Guardrails<br/>(safety, injection, sources)]
  EVAL --> OUTPUT[AI Response + Sources + Workflow Trace]
  OUTPUT --> UI
  UI --> U

  AGENT --> LOGS[AI Logs<br/>logs/pawpal_ai.log]

  TESTER[Pytest + Human Review] --> TESTS[tests/test_pawpal.py<br/>tests/test_ai_assistant.py]
  TESTS --> SCHED
  TESTS --> AGENT
```

## Data Flow

1. Input: user submits pet/tasks data or an AI question in the UI.
2. Process: scheduler builds a plan; agent retrieves notes, generates an answer, and self-checks it.
3. Output: UI displays schedule + AI response with sources and workflow trace; logs are saved.

## Human and Testing Checkpoints

- Human users review AI responses and can adjust plans/tasks in-app.
- Automated tests validate both scheduler logic and AI safety/reliability behavior.
