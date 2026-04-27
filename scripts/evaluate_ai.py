"""
Evaluation harness for PawPal+ AI enhancements.

Run with:
    python3 scripts/evaluate_ai.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_assistant import AIResponse, PetCareAssistant
from pawpal_system import Owner, Pet, Scheduler, Task


EVAL_SUITE_PATH = ROOT / "assets" / "eval_suite.json"
PRIMARY_KB = ROOT / "assets" / "pet_care_knowledge.md"
SECONDARY_KB = ROOT / "assets" / "pet_health_reference.md"
STYLE_MARKERS = ("Priority now:", "Watch for:", "Small next step:", "Encouragement:")


def build_owner_and_schedule() -> tuple[Owner, list]:
    owner = Owner(name="Jordan", day_start="08:00", day_end="20:00")

    mochi = Pet(name="Mochi", species="dog", age=4)
    luna = Pet(name="Luna", species="cat", age=6)

    mochi.add_task(Task(title="Morning walk", duration_minutes=30, priority="high"))
    mochi.add_task(Task(title="Feed breakfast", duration_minutes=10, priority="high", frequency="daily"))
    luna.add_task(Task(title="Clean litter box", duration_minutes=10, priority="medium", frequency="daily"))
    luna.add_task(Task(title="Medication", duration_minutes=5, priority="high"))

    owner.add_pet(mochi)
    owner.add_pet(luna)
    schedule = Scheduler(owner).build_schedule()
    return owner, schedule


def marker_score(answer: str) -> float:
    hits = sum(marker in answer for marker in STYLE_MARKERS)
    return hits / len(STYLE_MARKERS)


def avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def evaluate_rag(
    suite: dict,
    owner: Owner,
    schedule: list,
) -> dict:
    baseline = PetCareAssistant(
        enable_llm=False,
        knowledge_base_paths=[str(PRIMARY_KB)],
    )
    enhanced = PetCareAssistant(
        enable_llm=False,
        knowledge_base_paths=[str(PRIMARY_KB), str(SECONDARY_KB)],
    )

    baseline_hits = 0
    enhanced_hits = 0
    baseline_conf: list[float] = []
    enhanced_conf: list[float] = []

    for case in suite["rag_cases"]:
        base_resp = baseline.answer_question(case["question"], owner, schedule, style="balanced")
        enh_resp = enhanced.answer_question(case["question"], owner, schedule, style="balanced")

        baseline_titles = {item.title for item in base_resp.sources}
        enhanced_titles = {item.title for item in enh_resp.sources}
        expected = case["expected_title"]

        baseline_hits += int(expected in baseline_titles)
        enhanced_hits += int(expected in enhanced_titles)
        baseline_conf.append(base_resp.confidence)
        enhanced_conf.append(enh_resp.confidence)

    total = len(suite["rag_cases"])
    return {
        "baseline_hits": baseline_hits,
        "enhanced_hits": enhanced_hits,
        "total": total,
        "baseline_hit_rate": baseline_hits / total,
        "enhanced_hit_rate": enhanced_hits / total,
        "baseline_avg_conf": avg(baseline_conf),
        "enhanced_avg_conf": avg(enhanced_conf),
    }


def evaluate_agentic_steps(
    owner: Owner,
    schedule: list,
) -> dict:
    assistant = PetCareAssistant(enable_llm=False)
    prompts = [
        "How can I improve hydration and exercise balance?",
        "Create a practical evening care plan for both pets.",
        "What is one risk to watch in this schedule?",
    ]

    step_counts: list[float] = []
    required_steps = {"plan_intent", "retrieve_knowledge", "assess_schedule_risks", "draft_answer", "self_check"}
    required_hits = 0

    for prompt in prompts:
        response = assistant.answer_question(prompt, owner, schedule, style="balanced")
        step_counts.append(float(len(response.steps)))
        names = {step.name for step in response.steps}
        required_hits += int(required_steps.issubset(names))

    return {
        "prompts": len(prompts),
        "avg_steps": avg(step_counts),
        "required_step_full_hits": required_hits,
    }


def evaluate_specialization(
    suite: dict,
    owner: Owner,
    schedule: list,
) -> dict:
    assistant = PetCareAssistant(enable_llm=False)
    balanced_scores: list[float] = []
    coach_scores: list[float] = []

    for prompt in suite["style_cases"]:
        balanced = assistant.answer_question(prompt, owner, schedule, style="balanced")
        coach = assistant.answer_question(prompt, owner, schedule, style="calm_coach")
        balanced_scores.append(marker_score(balanced.answer))
        coach_scores.append(marker_score(coach.answer))

    return {
        "cases": len(suite["style_cases"]),
        "balanced_marker_rate": avg(balanced_scores),
        "coach_marker_rate": avg(coach_scores),
    }


def evaluate_guardrails(
    suite: dict,
    owner: Owner,
    schedule: list,
) -> dict:
    assistant = PetCareAssistant(enable_llm=False)
    passes = 0
    confidences: list[float] = []

    for case in suite["guardrail_cases"]:
        response: AIResponse = assistant.answer_question(case["question"], owner, schedule, style="balanced")
        ok = response.mode == case["expected_mode"] and response.guardrail_triggered
        passes += int(ok)
        confidences.append(response.confidence)

    total = len(suite["guardrail_cases"])
    return {
        "passes": passes,
        "total": total,
        "avg_confidence": avg(confidences),
    }


def main() -> int:
    suite = json.loads(EVAL_SUITE_PATH.read_text(encoding="utf-8"))
    owner, schedule = build_owner_and_schedule()

    rag = evaluate_rag(suite, owner, schedule)
    agentic = evaluate_agentic_steps(owner, schedule)
    style = evaluate_specialization(suite, owner, schedule)
    guardrails = evaluate_guardrails(suite, owner, schedule)

    checks = [
        ("RAG improved hit rate", rag["enhanced_hit_rate"] > rag["baseline_hit_rate"]),
        ("Agentic steps observable", agentic["avg_steps"] >= 5.0 and agentic["required_step_full_hits"] == agentic["prompts"]),
        ("Specialization measurably differs", (style["coach_marker_rate"] - style["balanced_marker_rate"]) >= 0.75),
        ("Guardrails pass benchmark", guardrails["passes"] == guardrails["total"]),
    ]

    print("=== PawPal+ Stretch Feature Evaluation ===")
    print(
        "RAG benchmark: "
        f"baseline {rag['baseline_hits']}/{rag['total']} ({rag['baseline_hit_rate']:.2f}) vs "
        f"enhanced {rag['enhanced_hits']}/{rag['total']} ({rag['enhanced_hit_rate']:.2f})"
    )
    print(
        "RAG confidence: "
        f"baseline {rag['baseline_avg_conf']:.2f} vs enhanced {rag['enhanced_avg_conf']:.2f}"
    )
    print(
        "Agentic workflow: "
        f"avg {agentic['avg_steps']:.1f} intermediate steps; "
        f"required-step coverage {agentic['required_step_full_hits']}/{agentic['prompts']}"
    )
    print(
        "Style specialization: "
        f"balanced marker rate {style['balanced_marker_rate']:.2f} vs "
        f"calm_coach marker rate {style['coach_marker_rate']:.2f}"
    )
    print(
        "Guardrails: "
        f"{guardrails['passes']}/{guardrails['total']} checks passed; "
        f"average confidence {guardrails['avg_confidence']:.2f}"
    )
    print("Checks:")
    for name, status in checks:
        mark = "PASS" if status else "FAIL"
        print(f"- {name}: {mark}")

    passed = sum(int(status) for _, status in checks)
    print(f"Overall: {passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
