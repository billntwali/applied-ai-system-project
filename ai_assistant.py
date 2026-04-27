"""
AI assistant layer for PawPal+.

This module adds Retrieval-Augmented Generation (RAG), basic safety guardrails,
and structured logging so AI behavior is traceable.
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


@dataclass(frozen=True)
class KnowledgeChunk:
    """A single retrievable knowledge chunk."""

    title: str
    content: str
    term_freq: Counter


@dataclass(frozen=True)
class RetrievedChunk:
    """A knowledge chunk with a retrieval score."""

    title: str
    content: str
    score: float


@dataclass(frozen=True)
class AIResponse:
    """AI answer plus metadata for UI/testing."""

    answer: str
    sources: list[RetrievedChunk]
    mode: str
    guardrail_triggered: bool
    workflow_trace: list[str]


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
    - retrieval over local pet-care notes
    - lightweight safety guardrails
    - optional OpenAI generation when API key is configured
    """

    def __init__(
        self,
        knowledge_base_path: str = "assets/pet_care_knowledge.md",
        model: str = "gpt-4.1-mini",
        api_key: Optional[str] = None,
        enable_llm: bool = True,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.model = model
        self.enable_llm = enable_llm
        self.knowledge_base_path = Path(knowledge_base_path)
        self.logger = logger or _default_logger(Path("logs/pawpal_ai.log"))
        self.chunks = self._load_knowledge_base(self.knowledge_base_path)
        self.client = None

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
    ) -> AIResponse:
        """Return an answer grounded in retrieved notes and today's schedule."""
        clean_question = question.strip()
        if not clean_question:
            return AIResponse(
                answer="Please ask a pet-care question so I can help.",
                sources=[],
                mode="guardrail_blocked",
                guardrail_triggered=True,
                workflow_trace=["blocked_empty_question"],
            )

        blocked_reason = self._guardrail_reason(clean_question)
        if blocked_reason:
            self._log_event("guardrail_blocked", question=clean_question, reason=blocked_reason)
            return AIResponse(
                answer=blocked_reason,
                sources=[],
                mode="guardrail_blocked",
                guardrail_triggered=True,
                workflow_trace=["guardrail_blocked"],
            )

        retrieved = self.retrieve(clean_question, top_k=3)
        schedule_context = self._schedule_context(owner, schedule or [])
        self._log_event(
            "retrieval_complete",
            question=clean_question,
            top_scores=[round(item.score, 4) for item in retrieved],
            sources=[item.title for item in retrieved],
        )

        workflow_trace = [
            "plan: retrieve relevant pet-care notes and summarize schedule context",
            "act: generate an initial grounded answer",
        ]

        if self.client is not None:
            try:
                draft_answer = self._answer_with_llm(clean_question, schedule_context, retrieved)
                self._log_event("llm_answer_success", model=self.model)
                checked_answer, check_notes = self._self_check_and_revise(
                    draft_answer=draft_answer,
                    schedule_context=schedule_context,
                    source_titles=[item.title for item in retrieved],
                )
                workflow_trace.append("check: validate citations and safety language")
                workflow_trace.extend(f"check_note: {item}" for item in check_notes)
                return AIResponse(
                    answer=checked_answer,
                    sources=retrieved,
                    mode="llm_agentic_rag",
                    guardrail_triggered=False,
                    workflow_trace=workflow_trace,
                )
            except Exception as exc:  # pragma: no cover - runtime fallback
                self._log_event("llm_answer_failed", error=str(exc))

        draft_answer = self._fallback_answer(clean_question, schedule_context, retrieved)
        checked_answer, check_notes = self._self_check_and_revise(
            draft_answer=draft_answer,
            schedule_context=schedule_context,
            source_titles=[item.title for item in retrieved],
        )
        workflow_trace.append("check: validate citations and safety language")
        workflow_trace.extend(f"check_note: {item}" for item in check_notes)
        return AIResponse(
            answer=checked_answer,
            sources=retrieved,
            mode="local_agentic_rag",
            guardrail_triggered=False,
            workflow_trace=workflow_trace,
        )

    def generate_daily_briefing(
        self,
        owner: Owner,
        schedule: Optional[list[ScheduledTask]] = None,
    ) -> AIResponse:
        """
        Agentic helper for the main schedule flow.
        Uses plan-act-check to produce a daily briefing even without a user question.
        """
        question = (
            "Create today's prioritized pet-care briefing with immediate actions, "
            "risks to watch, and one practical adjustment."
        )
        return self.answer_question(question=question, owner=owner, schedule=schedule)

    def retrieve(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        """Return top matching knowledge chunks based on lexical similarity."""
        query_tf = Counter(_tokenize(query))
        if not query_tf:
            return []

        scored: list[RetrievedChunk] = []
        for chunk in self.chunks:
            score = self._similarity(query_tf, chunk.term_freq)
            if score > 0:
                scored.append(RetrievedChunk(chunk.title, chunk.content, score))
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_knowledge_base(self, path: Path) -> list[KnowledgeChunk]:
        if not path.exists():
            raise FileNotFoundError(f"Knowledge base not found: {path}")

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

        chunks: list[KnowledgeChunk] = []
        for title, lines in sections:
            content = " ".join(lines)
            chunks.append(KnowledgeChunk(title=title, content=content, term_freq=Counter(_tokenize(content))))
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

    def _answer_with_llm(
        self,
        question: str,
        schedule_context: str,
        retrieved: list[RetrievedChunk],
    ) -> str:
        sources_text = "\n".join(
            f"[{idx + 1}] {item.title}: {item.content}"
            for idx, item in enumerate(retrieved)
        ) or "[none]"

        system_msg = (
            "You are PawPal+, an AI pet-care planning assistant. "
            "Use only the supplied schedule and retrieved notes. "
            "If unsure, state uncertainty. Keep advice practical and concise."
        )
        user_msg = (
            f"Question:\n{question}\n\n"
            f"Schedule context:\n{schedule_context}\n\n"
            f"Retrieved notes:\n{sources_text}\n\n"
            "Give a direct answer, then end with a short 'Sources used:' line listing note titles."
        )

        completion = self.client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_msg},
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
    ) -> str:
        source_titles = ", ".join(item.title for item in retrieved) if retrieved else "none"
        summary_lines = [
            "I used PawPal's local pet-care notes and your schedule to build this suggestion.",
        ]
        if retrieved:
            top = retrieved[0]
            summary_lines.append(f"Best matching guidance: {top.title}. {top.content}")
        else:
            summary_lines.append("I did not find a close match in the notes, so this is a conservative plan.")
        summary_lines.append(f"Schedule snapshot: {schedule_context}")
        summary_lines.append(f"Question: {question}")
        summary_lines.append(f"Sources used: {source_titles}")
        return "\n".join(summary_lines)

    def _self_check_and_revise(
        self,
        draft_answer: str,
        schedule_context: str,
        source_titles: list[str],
    ) -> tuple[str, list[str]]:
        """
        Agentic "check" phase.
        Ensures the draft contains source attribution and avoids unsafe phrasing.
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

    def _log_event(self, event_type: str, **payload: object) -> None:
        record = {"event": event_type, **payload}
        self.logger.info(json.dumps(record, default=str))
