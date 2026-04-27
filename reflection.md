# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

The initial UML contains five classes across two layers — two plain classes and three dataclasses.

| Class | Type | Responsibility |
|-------|------|----------------|
| `Task` | dataclass | Holds a single care activity: its title, how long it takes, priority level, optional preferred time of day, and whether it is required. Pure data — no behaviour. |
| `ScheduledTask` | dataclass | Wraps a `Task` once it has been placed on the timeline, adding a start time, end time, and a human-readable reason explaining why it was chosen. |
| `Pet` | class | Stores a pet's profile (name, species, age, breed, special needs) and owns a collection of `Task` objects. Responsible for managing the list of tasks that belong to that pet. |
| `Owner` | class | Stores the owner's profile and their daily availability window (day_start / day_end). Owns a collection of `Pet` objects and is the single entry point for adding or removing pets. |
| `Scheduler` | class | Contains the scheduling intelligence. Given an `Owner` (and through it, all pets and tasks), it prioritises tasks (high → medium → low), fits them into the available time window, and produces an ordered list of `ScheduledTask` objects along with a plain-English explanation. |

Relationships: `Owner` has one-to-many `Pet`; `Pet` has zero-to-many `Task`; `Scheduler` takes one `Owner` and produces zero-to-many `ScheduledTask`, each of which wraps exactly one `Task`.

**b. Design changes**

After reviewing the skeleton, two issues were identified and fixed:

1. **Added `pet_name: str` to `ScheduledTask`.**
   The original design had no way to know which pet a scheduled task belonged to. Without this field, `explain_plan` could only say "Walk at 08:00" — it couldn't say "Walk *Mochi* at 08:00". This matters especially when an owner has multiple pets whose tasks get merged into a single timeline. Adding `pet_name` directly to `ScheduledTask` was the simplest fix: no extra lookup needed when generating the explanation.

2. **Removed the unused `field` import from `dataclasses`.**
   The original skeleton imported `field` from `dataclasses` but never used it. Removing it keeps the imports honest and avoids confusion during implementation.

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

The scheduler considers three constraints, in order of importance:

1. **Required vs optional** — required tasks are always scheduled before optional ones, regardless of priority. A pet must be fed even if a playtime session would rank higher by priority alone.
2. **Priority level** (high → medium → low) — within each required/optional bucket, high-priority tasks get the earliest slots.
3. **Available time window** (owner's `day_start` / `day_end`) — tasks that would push past `day_end` are skipped rather than truncated, so no task ever runs over the owner's available hours.

Required tasks were ranked first because missing them (feeding, medication) has real welfare consequences, while missing optional tasks (playtime, grooming) is merely inconvenient.

**b. Tradeoffs**

The conflict detector checks for *exact time-window overlap* (`A.start < B.end AND B.start < A.end`) rather than accounting for gaps between tasks. This means two tasks scheduled back-to-back with zero minutes between them — say, a 30-minute walk ending at 08:30 followed immediately by a 10-minute feeding at 08:30 — are treated as conflict-free even though a real owner would need at least a moment to transition between them.

This tradeoff is reasonable for this scenario because the app is a planning aid, not a rigid timer. A small gap between tasks is a natural human behaviour that doesn't need to be modelled explicitly at this stage. If PawPal+ were extended to handle professional pet-sitters managing many pets on tight schedules, adding a configurable "buffer time" between tasks would be the right next step. For a single busy owner, exact-overlap detection is sufficient to catch real mistakes (like accidentally double-booking the same time slot for two pets) without producing false warnings on normal back-to-back scheduling.

---

## 3. AI Collaboration

**a. How you used AI**

AI tools were used at every stage, but with different intensities:

- **Design (Phase 1):** Used AI to generate the initial Mermaid UML from a plain-English description of the four classes. The most effective prompt pattern was *"Here are the classes I need and their responsibilities — generate a class diagram showing relationships."* Providing the responsibility first (rather than just a name) produced much more accurate diagrams.
- **Skeleton generation (Phase 1):** Asked AI to translate the UML into Python dataclasses and class stubs. The prompt *"Use Python dataclasses for Task and ScheduledTask, regular classes for Pet and Owner"* gave clean output that matched our architectural intent.
- **Logic implementation (Phases 2–4):** Used AI in agent mode to implement `build_schedule`, sorting, filtering, recurring tasks, and conflict detection. The most helpful prompts were narrow and specific: *"How should Scheduler retrieve all tasks from all pets given that Owner.get_pets() returns a list?"* — concrete, scoped questions with a code reference produced better results than open-ended requests.
- **Test generation (Phase 5):** Asked AI to suggest edge cases beyond happy-path scenarios. The prompt *"What edge cases should I test for a scheduler with recurring tasks and conflict detection?"* surfaced the empty-list, no-pets, and same-start-time cases that weren't immediately obvious.
- **Debugging:** When a test failed, the most effective prompt pattern was to paste the exact error and ask *"Is the bug in the test or in the implementation?"* — this forced a diagnostic response rather than a blind rewrite.

**b. Judgment and verification**

During conflict detection, the AI initially suggested using a `datetime` comparison that parsed both `start_time` and `end_time` strings into full `datetime` objects on every comparison. The logic was correct, but it was significantly more verbose than needed. Since our time values are already zero-padded `HH:MM` strings, they sort and compare correctly as plain strings — `"08:00" < "08:30"` is `True` in Python without any parsing.

The AI suggestion was rejected in favour of the direct string comparison `a.start_time < b.end_time and b.start_time < a.end_time`. To verify this was safe, the edge cases in the test suite (same start time, back-to-back, overlapping) were run against both versions — they produced identical results. The simpler version was kept because it is easier to read, has no imports, and cannot fail on malformed datetime input.

This was a good reminder that AI tends to reach for the most general tool (full datetime parsing) even when a simpler one is sufficient. The lead architect's job is to recognise when that generalisation adds complexity without adding value.

---

## 4. Testing and Verification

**a. What you tested**

The test suite covers 27 behaviours across five areas:

| Area | Key behaviours verified |
|------|------------------------|
| Task lifecycle | `mark_complete()` changes status; one-off tasks return `None`; daily/weekly tasks return a correctly dated successor without mutating the original |
| Pet management | `add_task()` grows the internal list; `get_tasks()` returns a defensive copy so external mutations don't corrupt state |
| Owner management | `add_pet()` registers correctly; `remove_pet()` drops exactly the named pet and leaves others intact |
| Scheduler core | Priority ordering (high before low, required before optional); time-window enforcement (tasks that exceed `day_end` are skipped); completed tasks are excluded from new schedules; owner with no pets and pet with no tasks produce no errors |
| Algorithms | `sort_by_time` on unsorted and empty inputs; `filter_tasks` by pet name, completion status, and both combined; `complete_task` auto-spawns next occurrence for recurring tasks and does not for one-off tasks; `detect_conflicts` catches exact same-start-time, partial overlap, and correctly passes back-to-back and single-task inputs |

These tests matter because the scheduler's output directly affects a pet's welfare. A bug in priority ordering or time-window enforcement could mean a feeding task gets skipped in favour of playtime — which is a real functional failure, not just a cosmetic one.

**b. Confidence**

**4 / 5 stars.** All 27 tests pass cleanly. Confidence is high for the core scheduling logic and algorithmic methods. The remaining gap is input validation: the system does not guard against malformed `HH:MM` strings (e.g. `"25:99"`), negative `duration_minutes`, or an unknown `frequency` value. These could cause silent failures or confusing errors in production. Given more time, the next tests to add would be:

1. `Task(duration_minutes=-5)` — should raise a `ValueError` or be rejected
2. `Owner(day_start="invalid")` — should be caught at construction, not at schedule time
3. A schedule where every task is skipped because all are too long — verify `explain_plan` handles an empty list gracefully (it does, but it's not explicitly tested)

---

## 5. Reflection

**a. What went well**

The cleanest part of the project is the separation between the logic layer (`pawpal_system.py`) and the UI layer (`app.py`). Because `Scheduler`, `Owner`, `Pet`, and `Task` know nothing about Streamlit, every method could be developed and tested in pure Python before touching the UI. This meant debugging was fast — a failing test pinpointed the exact method without needing to run the browser app. The `st.session_state` pattern for persisting the `Owner` object also worked well; once that pattern was established, adding new UI features (tabs, filters, mark-complete buttons) was straightforward.

**b. What you would improve**

Two things stand out:

1. **Persistence across browser refreshes.** Currently all data lives in `st.session_state`, which is lost when the page is refreshed or the server restarts. A real version of this app would need a lightweight database (SQLite via `sqlite3` or a simple JSON file) to persist the owner's pets and tasks between sessions.
2. **The `build_schedule` strategy.** The current greedy approach fills time slots in priority order and skips tasks that don't fit. This means a 60-minute walk at high priority can block a 5-minute feeding at medium priority from its preferred morning slot. A smarter approach would attempt to fit skipped tasks later in the day, or allow the owner to specify hard time anchors (e.g. "always feed at 07:30").

**c. Key takeaway**

The most important lesson was about *staying the architect*. AI tools are extremely good at generating plausible code quickly, but "plausible" is not the same as "correct for this design." At several points the AI generated code that worked in isolation but violated the design — for example, adding logic directly to `Task.mark_complete()` that reached outside the class to update a pet's task list, coupling two objects that should be independent. Catching those violations required reading the generated code critically, not just running the tests. The tests passing is a necessary condition for correctness, but not a sufficient one — the code also needs to respect the boundaries the architecture established. Working with AI effectively means treating it as a fast junior developer: review everything, accept what fits, rewrite what doesn't.

---

## 6. Responsible AI Reflection (Short)

### Limitations and Biases

- Retrieval is lexical, so the assistant can miss relevant guidance when a user uses very different wording.
- The knowledge base reflects a limited set of pet-care assumptions and may not generalize to all homes or medical contexts.
- Confidence is a heuristic signal for reliability, not a calibrated probability of truth.

### Misuse Risk and Mitigations

- Potential misuse includes prompt-injection attempts and requests for unsafe medical advice.
- The system mitigates this with guardrails: injection-style prompts are blocked, emergency language triggers escalation messaging, and responses include source traceability.
- Logging (`logs/pawpal_ai.log`) records key events to support debugging and accountability.

### Reliability Surprise

- The biggest surprise was that low-context answers could still look plausible.
- Confidence scoring plus explicit weak-context tests made this visible and easier to monitor.

### Collaboration with AI During Development

- Helpful AI suggestion: using a clear separation between deterministic scheduling and an AI copilot improved testability and made failures easier to isolate.
- Flawed AI suggestion: an early suggestion implied that retrieval alone was enough evidence of quality; in practice I needed explicit reliability checks, confidence reporting, and guardrail tests to show the system was trustworthy.
