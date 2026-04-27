# PawPal+ System Diagram

```mermaid
flowchart LR
  U[Human User] --> UI[Streamlit UI<br/>app.py]

  UI --> SCHED[Deterministic Scheduler<br/>pawpal_system.py]
  UI --> AGENT[AI Copilot (Agentic)<br/>ai_assistant.py]

  AGENT --> RETRIEVER[Multi-Source Retriever]
  RETRIEVER --> KB1[assets/pet_care_knowledge.md]
  RETRIEVER --> KB2[assets/pet_health_reference.md]
  SCHED --> CONTEXT[Schedule Context]
  RETRIEVER --> GENERATOR[Answer Generation<br/>LLM or Local Fallback]
  CONTEXT --> GENERATOR

  GENERATOR --> EVAL[Self-Check + Guardrails<br/>(safety, injection, sources)]
  EVAL --> OUTPUT[AI Response + Sources + Confidence + Step Trace]
  OUTPUT --> UI
  UI --> U

  AGENT --> LOGS[AI Logs<br/>logs/pawpal_ai.log]

  TESTER[Pytest + Human Review] --> TESTS[tests/test_pawpal.py<br/>tests/test_ai_assistant.py]
  TESTS --> SCHED
  TESTS --> AGENT
  HARNESS[scripts/evaluate_ai.py] --> AGENT
  HARNESS --> SCORE[Benchmark Summary<br/>hit rates, style deltas, pass/fail]
```

## Data Flow

1. Input: user submits pet/tasks data or an AI question in the UI.
2. Process: scheduler builds a plan; agent retrieves from multiple knowledge sources, drafts an answer, and self-checks it.
3. Output: UI displays schedule + AI response with sources, confidence, and intermediate workflow steps; logs are saved.

## Human and Testing Checkpoints

- Human users review AI responses and can adjust plans/tasks in-app.
- Automated tests validate both scheduler logic and AI safety/reliability behavior.
- The evaluation harness benchmarks measurable quality deltas for RAG, specialization, and guardrails.
