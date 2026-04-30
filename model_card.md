# Model Card: PawPal+ AI Copilot

## 1. Model Details
- Model/System Name: PawPal+ AI Copilot
- Version: v1.0 (course final submission)
- Date Updated: April 29, 2026
- Base Project: PawPal+ daily pet-care scheduler
- Core AI Module: `ai_assistant.py`
- Default Runtime Mode: local agentic RAG fallback (OpenAI mode optional via `OPENAI_API_KEY`)

## 2. Intended Use
- Primary purpose: provide grounded pet-care planning guidance based on schedule context and local knowledge notes.
- Primary users: pet owners organizing daily care tasks.
- Output types:
  - prioritized daily briefing
  - Q&A grounded in local pet-care notes
  - source-attributed recommendations with confidence proxy
- Human-in-the-loop expectation: users review and decide actions; this system is advisory.

## 3. Out-of-Scope / Non-Intended Use
- Not a veterinary diagnostic tool.
- Not emergency medical triage beyond escalation guidance.
- Not safe for autonomous medication dosing decisions without veterinarian confirmation.
- Not designed for legal, insurance, or clinical record decisions.

## 4. Data and Knowledge Sources
- `assets/pet_care_knowledge.md`
- `assets/pet_health_reference.md`
- user-provided schedule context from `pawpal_system.py`

Retrieval is lexical similarity over local text chunks (not internet search, not vector DB).

## 5. System Behavior Summary
The assistant follows a structured chain:
1. infer user intent
2. retrieve relevant local knowledge chunks
3. assess schedule risk flags
4. draft answer (LLM if enabled, otherwise local fallback)
5. self-check for source attribution and safety language

Each response includes:
- answer text
- source list
- confidence score (heuristic)
- workflow trace + observable agent steps

## 6. Reflection Prompt Answers

### A) How AI collaboration was used
- AI support was used for architecture iteration, retrieval workflow design, guardrail shaping, and test case expansion.
- Effective prompt pattern: constrained requests tied to exact module boundaries (for example, scheduler logic vs assistant logic) produced better outputs than broad prompts.

### B) Helpful AI suggestion
- Separating deterministic scheduling from the AI assistant was a strong suggestion.
- Benefit: easier testing, clearer responsibilities, and safer fallbacks when generation is unavailable.

### C) Flawed AI suggestion and correction
- A flawed suggestion implied retrieval presence alone was enough to claim quality.
- Correction: added explicit evaluation checks (`scripts/evaluate_ai.py`), confidence reporting, and guardrail benchmarks so quality claims are measurable.

### D) Judgment and verification process
- AI-generated ideas were accepted only after tests/harness checks passed and implementation fit system boundaries.
- When suggestions increased complexity without clear value, simpler deterministic alternatives were retained.

## 7. Limitations and Biases
- Lexical retrieval bias: semantically relevant answers may be missed if wording differs from local documents.
- Coverage bias: outputs reflect the scope and assumptions of the two curated knowledge files.
- Confidence limitation: confidence is a heuristic indicator, not a calibrated probability of correctness.
- Domain limitation: recommendations can sound plausible even when context is sparse.

## 8. Misuse Risks and Mitigations
- Misuse risks:
  - prompt injection attempts
  - over-trust in non-clinical advice
  - unsafe medication interpretation
- Mitigations:
  - injection-pattern blocking
  - emergency keyword escalation messaging
  - source attribution on responses
  - workflow logging in `logs/pawpal_ai.log`
  - explicit non-diagnostic positioning in docs

## 9. Testing and Evaluation Results
Latest local results (April 29, 2026):
- `python3 -m pytest -q`: **35 passed**
- `python3 scripts/evaluate_ai.py`: **4/4 checks passed**

Evaluation metrics:
- RAG hit rate: baseline **0/4 (0.00)** vs enhanced **4/4 (1.00)**
- RAG confidence: **0.58 -> 0.63**
- Agentic observability: **5.0 average intermediate steps**, required-step coverage **3/3**
- Style specialization marker rate: **0.00 (balanced)** vs **1.00 (calm_coach)**
- Guardrail checks: **2/2 passed**, average confidence **0.99**

## 10. What Was Surprising During Reliability Testing
- Guardrails were consistently easy to validate.
- The bigger reliability risk was polished-but-weak answers under thin context, which became visible only after adding confidence + benchmark instrumentation.

## 11. Responsible Deployment Notes
- Keep a human decision-maker in the loop for all care actions.
- For emergencies, contact a veterinarian or poison hotline immediately.
- Re-run tests and evaluation harness after any prompt/knowledge/logic change.

