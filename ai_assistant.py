"""
AI assistant layer for PawPal+.

This module adds multi-source RAG, agentic workflow tracing, style specialization,
and structured logging so behavior is observable and testable.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from typing import Optional

from pawpal_system import Owner, ScheduledTask

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency for test environments
    OpenAI = None


WORD_RE = re.compile(r"[a-zA-Z0-9']+")
INJECTION_PATTERNS = (
    "ignore previous",
    "ignore all previous",
    "system prompt",
    "developer message",
    "bypass safety",
    "jailbreak",
    "reveal prompt",
)
EMERGENCY_KEYWORDS = (
    "not breathing",
    "can't breathe",
    "cannot breathe",
    "collapsed",
    "seizure",
    "poison",
    "poisoned",
    "bleeding",
    "unresponsive",
)
STYLE_PRESETS = ("balanced", "calm_coach")


@dataclass(frozen=True)
class KnowledgeChunk:
    """A single retrievable knowledge chunk."""

    title: str
    content: str
    term_freq: Counter
    source: str


@dataclass(frozen=True)
class RetrievedChunk:
    """A knowledge chunk with retrieval score and source metadata."""

    title: str
    content: str
    score: float
    source: str


@dataclass(frozen=True)
class AgentStep:
    """Observable intermediate step in the agentic workflow."""

    name: str
    observation: str


@dataclass(frozen=True)
class AIResponse:
    """AI answer plus metadata for UI/testing."""

    answer: str
    sources: list[RetrievedChunk]
    mode: str
    guardrail_triggered: bool
    workflow_trace: list[str]
    confidence: float
    steps: list[AgentStep]
    style: str


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in WORD_RE.findall(text)]


def _default_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("pawpal_ai")
    if logger.handlers:
        return logger
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


class PetCareAssistant:
    """
    RAG-enabled assistant with:
    - retrieval over multiple local pet-care sources
    - agentic plan -> retrieve -> draft -> check workflow
    - optional style specialization (baseline vs calm-coach)
    - lightweight safety guardrails
    - optional OpenAI generation when API key is configured
    """

    def __init__(
        self,
        knowledge_base_path: str = "assets/pet_care_knowledge.md",
        knowledge_base_paths: Optional[list[str]] = None,
        model: str = "gpt-4.1-mini",
        api_key: Optional[str] = None,
        enable_llm: bool = True,
        default_style: str = "balanced",
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.model = model
        self.enable_llm = enable_llm
        self.default_style = self._normalize_style(default_style)
        self.logger = logger or _default_logger(Path("logs/pawpal_ai.log"))
        self.client = None

        raw_paths = knowledge_base_paths or [
            knowledge_base_path,
            "assets/pet_health_reference.md",
        ]
        # Preserve order but remove duplicates.
        deduped_paths: list[str] = []
        for item in raw_paths:
            if item not in deduped_paths:
                deduped_paths.append(item)
        self.knowledge_paths = [Path(path) for path in deduped_paths]
        self.chunks = self._load_knowledge_bases(self.knowledge_paths)

        resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")
        if self.enable_llm and resolved_api_key and OpenAI is not None:
            self.client = OpenAI(api_key=resolved_api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def answer_question(
        self,
        question: str,
        owner: Owner,
        schedule: Optional[list[ScheduledTask]] = None,
        style: Optional[str] = None,
    ) -> AIResponse:
        """Return an answer grounded in retrieved notes and schedule context."""
        active_style = self._normalize_style(style or self.default_style)
        clean_question = question.strip()
        steps: list[AgentStep] = []

        if not clean_question:
            steps.append(AgentStep(name="guardrail_empty_question", observation="empty input blocked"))
            return AIResponse(
                answer="Please ask a pet-care question so I can help.",
                sources=[],
                mode="guardrail_blocked",
                guardrail_triggered=True,
                workflow_trace=["blocked_empty_question"],
                confidence=0.99,
                steps=steps,
                style=active_style,
            )

        blocked_reason = self._guardrail_reason(clean_question)
        if blocked_reason:
            self._log_event("guardrail_blocked", question=clean_question, reason=blocked_reason)
            steps.append(AgentStep(name="guardrail_blocked", observation=blocked_reason))
            return AIResponse(
                answer=blocked_reason,
                sources=[],
                mode="guardrail_blocked",
                guardrail_triggered=True,
                workflow_trace=["guardrail_blocked"],
                confidence=0.99,
                steps=steps,
                style=active_style,
            )

        intent = self._infer_intent(clean_question)
        workflow_trace = [f"plan: inferred intent={intent}"]
        steps.append(AgentStep(name="plan_intent", observation=f"intent={intent}"))

        retrieved = self.retrieve(clean_question, top_k=4)
        source_names = sorted({item.source for item in retrieved})
        retrieval_observation = (
            f"{len(retrieved)} chunks from {len(source_names)} sources: {', '.join(source_names) or 'none'}"
        )
        steps.append(AgentStep(name="retrieve_knowledge", observation=retrieval_observation))
        workflow_trace.append("plan: selected retrieval context from local knowledge sources")

        schedule_data = schedule or []
        schedule_context = self._schedule_context(owner, schedule_data)
        risk_flags = self._assess_schedule_risks(schedule_data)
        steps.append(AgentStep(name="assess_schedule_risks", observation=", ".join(risk_flags)))
        workflow_trace.append("plan: summarized schedule context and risk flags")

        self._log_event(
            "retrieval_complete",
            question=clean_question,
            style=active_style,
            top_scores=[round(item.score, 4) for item in retrieved],
            sources=[f"{item.source}:{item.title}" for item in retrieved],
            intent=intent,
            risk_flags=risk_flags,
        )

        confidence = self._estimate_confidence(
            retrieved=retrieved,
            has_schedule_context=bool(schedule_data),
            using_llm=self.client is not None,
            risk_flags=risk_flags,
        )

        if self.client is not None:
            try:
                draft_answer = self._answer_with_llm(
                    question=clean_question,
                    schedule_context=schedule_context,
                    retrieved=retrieved,
                    style=active_style,
                    intent=intent,
                    risk_flags=risk_flags,
                )
                mode = "llm_agentic_rag"
                self._log_event("llm_answer_success", model=self.model, style=active_style)
                steps.append(AgentStep(name="draft_answer", observation=f"generated via {mode}"))
            except Exception as exc:  # pragma: no cover - runtime fallback
                self._log_event("llm_answer_failed", error=str(exc), style=active_style)
                draft_answer = self._fallback_answer(
                    question=clean_question,
                    schedule_context=schedule_context,
                    retrieved=retrieved,
                    style=active_style,
                    intent=intent,
                    risk_flags=risk_flags,
                )
                mode = "local_agentic_rag"
                steps.append(AgentStep(name="draft_answer", observation=f"llm failed; fallback used ({exc})"))
        else:
            draft_answer = self._fallback_answer(
                question=clean_question,
                schedule_context=schedule_context,
                retrieved=retrieved,
                style=active_style,
                intent=intent,
                risk_flags=risk_flags,
            )
            mode = "local_agentic_rag"
            steps.append(AgentStep(name="draft_answer", observation="generated via local fallback"))

        checked_answer, check_notes = self._self_check_and_revise(
            draft_answer=draft_answer,
            schedule_context=schedule_context,
            source_titles=[item.title for item in retrieved],
        )
        steps.append(AgentStep(name="self_check", observation=", ".join(check_notes)))

        workflow_trace.append("act: generated grounded draft response")
        workflow_trace.append("check: validated citations and safety language")
        workflow_trace.extend(f"check_note: {item}" for item in check_notes)

        self._log_event(
            "answer_complete",
            mode=mode,
            style=active_style,
            confidence=round(confidence, 4),
            step_count=len(steps),
        )

        return AIResponse(
            answer=checked_answer,
            sources=retrieved,
            mode=mode,
            guardrail_triggered=False,
            workflow_trace=workflow_trace,
            confidence=confidence,
            steps=steps,
            style=active_style,
        )

    def generate_daily_briefing(
        self,
        owner: Owner,
        schedule: Optional[list[ScheduledTask]] = None,
        style: Optional[str] = None,
    ) -> AIResponse:
        """Agentic helper for the main schedule flow."""
        question = (
            "Create today's prioritized pet-care briefing with immediate actions, "
            "risks to watch, and one practical adjustment."
        )
        return self.answer_question(
            question=question,
            owner=owner,
            schedule=schedule,
            style=style,
        )

    def retrieve(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        """Return top matching chunks from all configured knowledge sources."""
        query_tf = Counter(_tokenize(query))
        if not query_tf:
            return []

        scored: list[RetrievedChunk] = []
        for chunk in self.chunks:
            score = self._similarity(query_tf, chunk.term_freq)
            if score > 0:
                scored.append(RetrievedChunk(chunk.title, chunk.content, score, chunk.source))
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_knowledge_bases(self, paths: list[Path]) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        for path in paths:
            chunks.extend(self._load_knowledge_base(path))
        return chunks

    def _load_knowledge_base(self, path: Path) -> list[KnowledgeChunk]:
        if not path.exists():
            self.logger.warning(f"Knowledge base not found, skipping: {path}")
            return []

        text = path.read_text(encoding="utf-8")
        sections: list[tuple[str, list[str]]] = []
        current_title = "General Pet Care"
        current_lines: list[str] = []

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("## "):
                if current_lines:
                    sections.append((current_title, current_lines))
                current_title = line[3:].strip()
                current_lines = []
                continue
            if line:
                current_lines.append(line)
        if current_lines:
            sections.append((current_title, current_lines))

        source_name = path.name
        chunks: list[KnowledgeChunk] = []
        for title, lines in sections:
            content = " ".join(lines)
            chunks.append(
                KnowledgeChunk(
                    title=title,
                    content=content,
                    term_freq=Counter(_tokenize(content)),
                    source=source_name,
                )
            )
        return chunks

    def _similarity(self, query_tf: Counter, chunk_tf: Counter) -> float:
        overlap = set(query_tf).intersection(chunk_tf)
        if not overlap:
            return 0.0
        dot = sum(query_tf[token] * chunk_tf[token] for token in overlap)
        query_norm = sqrt(sum(value * value for value in query_tf.values()))
        chunk_norm = sqrt(sum(value * value for value in chunk_tf.values()))
        if query_norm == 0 or chunk_norm == 0:
            return 0.0
        return dot / (query_norm * chunk_norm)

    def _guardrail_reason(self, question: str) -> Optional[str]:
        lower_q = question.lower()

        for pattern in INJECTION_PATTERNS:
            if pattern in lower_q:
                return (
                    "I can help with pet-care planning, but I can't follow prompt-injection or "
                    "system-override requests."
                )

        for keyword in EMERGENCY_KEYWORDS:
            if keyword in lower_q:
                return (
                    "This sounds like a medical emergency. Please contact an emergency veterinarian "
                    "or pet poison hotline immediately."
                )
        return None

    def _schedule_context(self, owner: Owner, schedule: list[ScheduledTask]) -> str:
        if not schedule:
            return (
                f"Owner: {owner.name}. No scheduled tasks yet. "
                f"Availability window: {owner.day_start}-{owner.day_end}."
            )
        lines = [f"Owner: {owner.name}. Availability window: {owner.day_start}-{owner.day_end}."]
        lines.append("Today's scheduled tasks:")
        for item in schedule[:8]:
            lines.append(
                f"- {item.start_time}-{item.end_time}: {item.pet_name} -> "
                f"{item.task.title} ({item.task.priority}, {item.task.duration_minutes} min)"
            )
        return "\n".join(lines)

    def _assess_schedule_risks(self, schedule: list[ScheduledTask]) -> list[str]:
        if not schedule:
            return ["no_schedule_context"]

        risks: list[str] = []
        if len(schedule) >= 7:
            risks.append("heavy_task_load")
        if any(item.task.duration_minutes >= 45 for item in schedule):
            risks.append("long_single_task_block")
        if any(item.task.priority == "high" and item.start_time >= "18:00" for item in schedule):
            risks.append("late_high_priority_task")
        if not risks:
            risks.append("no_obvious_schedule_risks")
        return risks

    def _infer_intent(self, question: str) -> str:
        lower_q = question.lower()
        if "medicat" in lower_q or "dose" in lower_q:
            return "medication"
        if "walk" in lower_q or "exercise" in lower_q or "play" in lower_q:
            return "activity"
        if "safe" in lower_q or "risk" in lower_q:
            return "safety"
        if "briefing" in lower_q or "plan" in lower_q:
            return "planning"
        return "general_care"

    def _normalize_style(self, style: str) -> str:
        value = style.strip().lower()
        return value if value in STYLE_PRESETS else "balanced"

    def _answer_with_llm(
        self,
        question: str,
        schedule_context: str,
        retrieved: list[RetrievedChunk],
        style: str,
        intent: str,
        risk_flags: list[str],
    ) -> str:
        sources_text = "\n".join(
            f"[{idx + 1}] ({item.source}) {item.title}: {item.content}"
            for idx, item in enumerate(retrieved)
        ) or "[none]"

        base_system = (
            "You are PawPal+, an AI pet-care planning assistant. "
            "Use only the supplied schedule and retrieved notes. "
            "If unsure, state uncertainty."
        )
        if style == "calm_coach":
            style_block = (
                "Specialized style mode: calm_coach.\n"
                "Use this exact structure:\n"
                "Priority now: <one concrete action>\n"
                "Watch for: <one risk signal>\n"
                "Small next step: <one low-effort action>\n"
                "Encouragement: <one short supportive line>\n"
                "Sources used: <comma-separated note titles>"
            )
        else:
            style_block = (
                "Style mode: balanced.\n"
                "Provide concise practical guidance and end with 'Sources used: ...'."
            )

        user_msg = (
            f"Question:\n{question}\n\n"
            f"Intent:\n{intent}\n\n"
            f"Schedule context:\n{schedule_context}\n\n"
            f"Risk flags:\n{', '.join(risk_flags)}\n\n"
            f"Retrieved notes:\n{sources_text}\n\n"
            "Answer using only this context."
        )

        completion = self.client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": f"{base_system}\n\n{style_block}"},
                {"role": "user", "content": user_msg},
            ],
        )
        content = completion.choices[0].message.content
        return (content or "").strip() or "I could not generate an answer right now."

    def _fallback_answer(
        self,
        question: str,
        schedule_context: str,
        retrieved: list[RetrievedChunk],
        style: str,
        intent: str,
        risk_flags: list[str],
    ) -> str:
        source_titles = ", ".join(item.title for item in retrieved) if retrieved else "none"
        top_guidance = (
            f"{retrieved[0].title}. {retrieved[0].content}" if retrieved else
            "No close match found; provide a conservative plan and monitor closely."
        )

        if style == "calm_coach":
            watch_for = (
                "Watch for: stress, appetite, hydration, and medication timing changes."
                if "no_schedule_context" in risk_flags else
                f"Watch for: {', '.join(risk_flags)}."
            )
            lines = [
                f"Priority now: Start with the highest-priority required task and keep timing consistent.",
                watch_for,
                "Small next step: Set one reminder for the next critical task in today's window.",
                f"Encouragement: A steady routine is more valuable than a perfect routine.",
                f"Guidance focus ({intent}): {top_guidance}",
                f"Schedule snapshot: {schedule_context}",
                f"Question: {question}",
                f"Sources used: {source_titles}",
            ]
            return "\n".join(lines)

        summary_lines = [
            "I used PawPal's local pet-care notes and your schedule to build this suggestion.",
            f"Best matching guidance: {top_guidance}",
            f"Intent: {intent}",
            f"Risk flags: {', '.join(risk_flags)}",
            f"Schedule snapshot: {schedule_context}",
            f"Question: {question}",
            f"Sources used: {source_titles}",
        ]
        return "\n".join(summary_lines)

    def _self_check_and_revise(
        self,
        draft_answer: str,
        schedule_context: str,
        source_titles: list[str],
    ) -> tuple[str, list[str]]:
        """
        Agentic "check" phase.
        Ensures source attribution and basic safety language constraints.
        """
        notes: list[str] = []
        revised = draft_answer.strip()
        source_label = ", ".join(source_titles) if source_titles else "none"

        if "Sources used:" not in revised:
            revised = f"{revised}\nSources used: {source_label}"
            notes.append("added_missing_source_line")

        unsafe_phrases = ("double the dose", "ignore your vet", "skip medication")
        lowered = revised.lower()
        for phrase in unsafe_phrases:
            if phrase in lowered:
                revised += (
                    "\nSafety note: Medication dosing decisions should be confirmed with your veterinarian."
                )
                notes.append("added_medication_safety_note")
                break

        if "No scheduled tasks yet" in schedule_context and "No scheduled tasks yet" not in revised:
            revised += "\nNo scheduled tasks yet: generate today's schedule to personalize this guidance."
            notes.append("appended_missing_schedule_notice")

        if not notes:
            notes.append("no_changes_needed")
        return revised, notes

    def _estimate_confidence(
        self,
        retrieved: list[RetrievedChunk],
        has_schedule_context: bool,
        using_llm: bool,
        risk_flags: list[str],
    ) -> float:
        """
        Confidence proxy based on retrieval strength, source diversity, and context.
        Returns a bounded score in [0.0, 1.0].
        """
        if not retrieved:
            base = 0.32
        else:
            avg_score = sum(item.score for item in retrieved) / len(retrieved)
            source_diversity = len({item.source for item in retrieved})
            base = 0.42 + min(avg_score, 1.0) * 0.35 + min(source_diversity, 3) * 0.03

        if has_schedule_context:
            base += 0.08
        if using_llm:
            base += 0.04
        if "no_schedule_context" in risk_flags:
            base -= 0.03

        return max(0.0, min(base, 0.99))

    def _log_event(self, event_type: str, **payload: object) -> None:
        record = {"event": event_type, **payload}
        self.logger.info(json.dumps(record, default=str))
