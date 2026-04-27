import streamlit as st
from ai_assistant import AIResponse, PetCareAssistant
from pawpal_system import Owner, Pet, Task, Scheduler

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="wide")
st.title("🐾 PawPal+")
st.caption("A smart daily care planner with an agentic AI copilot.")


def clear_cached_outputs() -> None:
    """Clear generated schedule and AI outputs when core data changes."""
    for key in ("last_schedule", "ai_daily_brief", "ai_last_response"):
        st.session_state.pop(key, None)


def render_ai_response(response: AIResponse) -> None:
    """Reusable UI renderer for AI answers and trace metadata."""
    if response.guardrail_triggered:
        st.warning(response.answer)
    else:
        st.markdown(response.answer)

    sources = (
        ", ".join(f"{item.title} ({item.source})" for item in response.sources)
        if response.sources else
        "None"
    )
    st.caption(
        f"Mode: `{response.mode}` · Style: `{response.style}` · "
        f"Confidence: `{response.confidence:.2f}` · Sources: {sources}"
    )
    with st.expander("Agentic workflow trace", expanded=False):
        for step in response.workflow_trace:
            st.write(f"- {step}")
    with st.expander("Intermediate agent steps", expanded=False):
        rows = [{"Step": step.name, "Observation": step.observation} for step in response.steps]
        st.table(rows)

# ---------------------------------------------------------------------------
# Session state — Owner is created once and persisted across reruns
# ---------------------------------------------------------------------------
if "owner" not in st.session_state:
    st.session_state["owner"] = Owner(name="Jordan", day_start="08:00", day_end="20:00")
if "assistant_error" not in st.session_state:
    st.session_state["assistant_error"] = None
if "assistant" not in st.session_state:
    try:
        st.session_state["assistant"] = PetCareAssistant()
    except Exception as exc:
        st.session_state["assistant_error"] = str(exc)
        st.session_state["assistant"] = None

owner: Owner = st.session_state["owner"]
assistant: PetCareAssistant | None = st.session_state["assistant"]


# ---------------------------------------------------------------------------
# Sidebar: Owner settings
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Owner Settings")
    new_name  = st.text_input("Your name",         value=owner.name)
    new_start = st.text_input("Day start (HH:MM)",  value=owner.day_start)
    new_end   = st.text_input("Day end   (HH:MM)",  value=owner.day_end)
    if st.button("Save settings"):
        owner.name      = new_name
        owner.day_start = new_start
        owner.day_end   = new_end
        clear_cached_outputs()
        st.success(f"Saved for {owner.name}.")

    st.divider()
    mode_text = "LLM-backed mode (OPENAI_API_KEY found)" if assistant and assistant.client else "Local fallback mode (no API key)"
    st.caption(f"PawPal+ v2.0 · Agentic AI Project · {mode_text}")


# ---------------------------------------------------------------------------
# Main tabs
# ---------------------------------------------------------------------------
tab_pets, tab_schedule, tab_browse, tab_ai = st.tabs(
    ["🐾 Pets & Tasks", "📅 Today's Schedule", "🔍 Browse & Filter", "🤖 AI Copilot"]
)


# ===========================================================================
# Tab 1 — Pets & Tasks
# ===========================================================================
with tab_pets:

    # ---- Add pet -----------------------------------------------------------
    st.subheader("Your Pets")
    with st.form("add_pet_form", clear_on_submit=True):
        p1, p2, p3 = st.columns(3)
        with p1:
            pet_name = st.text_input("Pet name")
        with p2:
            species  = st.selectbox("Species", ["dog", "cat", "rabbit", "bird", "other"])
        with p3:
            age      = st.number_input("Age (years)", min_value=0, max_value=30, value=1)
        breed = st.text_input("Breed (optional)")
        add_pet_btn = st.form_submit_button("Add Pet")

    if add_pet_btn and pet_name.strip():
        owner.add_pet(Pet(
            name=pet_name.strip(), species=species,
            age=int(age), breed=breed.strip(),
        ))
        clear_cached_outputs()
        st.success(f"{pet_name.strip()} added!")

    pets = owner.get_pets()
    if pets:
        for pet in pets:
            label = f"**{pet.name}** — {pet.species}, age {pet.age}"
            if pet.breed:
                label += f", {pet.breed}"
            st.markdown(label)
    else:
        st.info("No pets yet. Add one above.")

    st.divider()

    # ---- Add task ----------------------------------------------------------
    st.subheader("Add a Task")
    if not pets:
        st.info("Add a pet first before adding tasks.")
    else:
        with st.form("add_task_form", clear_on_submit=True):
            selected_pet_name = st.selectbox("Assign to pet", [p.name for p in pets])
            t1, t2, t3 = st.columns(3)
            with t1:
                task_title = st.text_input("Task title", value="Morning walk")
            with t2:
                duration   = st.number_input("Duration (min)", min_value=1, max_value=240, value=20)
            with t3:
                priority   = st.selectbox("Priority", ["high", "medium", "low"])
            t4, t5, t6 = st.columns(3)
            with t4:
                time_pref  = st.selectbox("Preferred time", ["Any", "morning", "afternoon", "evening"])
            with t5:
                frequency  = st.selectbox("Frequency", ["once", "daily", "weekly"])
            with t6:
                is_required = st.checkbox("Required?", value=True)
            add_task_btn = st.form_submit_button("Add Task")

        if add_task_btn and task_title.strip():
            target = next(p for p in pets if p.name == selected_pet_name)
            target.add_task(Task(
                title=task_title.strip(),
                duration_minutes=int(duration),
                priority=priority,
                time_of_day=None if time_pref == "Any" else time_pref,
                frequency=frequency,
                is_required=is_required,
            ))
            clear_cached_outputs()
            st.success(f"'{task_title.strip()}' added to {selected_pet_name}.")

        # Show each pet's task list
        for pet in pets:
            tasks = pet.get_tasks()
            if tasks:
                with st.expander(f"{pet.name}'s tasks ({len(tasks)})"):
                    rows = [
                        {
                            "Title": t.title,
                            "Duration (min)": t.duration_minutes,
                            "Priority": t.priority,
                            "Frequency": t.frequency,
                            "Required": "yes" if t.is_required else "no",
                            "Done": "✓" if t.completed else "",
                        }
                        for t in tasks
                    ]
                    st.table(rows)


# ===========================================================================
# Tab 2 — Today's Schedule
# ===========================================================================
with tab_schedule:
    st.subheader("Today's Schedule")
    scheduler = Scheduler(owner)

    if st.button("Generate schedule", type="primary"):
        all_tasks = [t for p in owner.get_pets() for t in p.get_tasks()]
        if not all_tasks:
            st.warning("Add at least one task before generating a schedule.")
        else:
            st.session_state["last_schedule"] = scheduler.build_schedule()

    if "last_schedule" in st.session_state:
        schedule = st.session_state["last_schedule"]

        if not schedule:
            st.info("No tasks to schedule — all may already be completed, or none fit the time window.")
        else:
            # ---- Conflict warnings ----------------------------------------
            conflicts = scheduler.detect_conflicts(schedule)
            if conflicts:
                for w in conflicts:
                    st.warning(w)
            else:
                st.success(f"{len(schedule)} task(s) scheduled between {owner.day_start} and {owner.day_end} — no conflicts detected.")

            # ---- Sort toggle ----------------------------------------------
            sort_order = st.radio(
                "Display order",
                ["Priority order", "Chronological"],
                horizontal=True,
            )
            display = scheduler.sort_by_time(schedule) if sort_order == "Chronological" else schedule

            st.divider()

            # ---- Task cards -----------------------------------------------
            for i, entry in enumerate(display):
                col_info, col_btn = st.columns([6, 1])
                with col_info:
                    freq_badge  = f"  `{entry.task.frequency}`" if entry.task.frequency != "once" else ""
                    status_icon = "✅" if entry.task.completed else "🔲"
                    st.markdown(
                        f"{status_icon} **{entry.start_time} – {entry.end_time}** &nbsp;|&nbsp; "
                        f"**{entry.pet_name}**: {entry.task.title} "
                        f"({entry.task.duration_minutes} min, {entry.task.priority}){freq_badge}"
                    )
                    st.caption(entry.reason)
                with col_btn:
                    if not entry.task.completed:
                        if st.button("Mark done", key=f"done_{i}"):
                            target_pet = next(
                                p for p in owner.get_pets() if p.name == entry.pet_name
                            )
                            next_task = scheduler.complete_task(target_pet, entry.task)
                            clear_cached_outputs()
                            if next_task:
                                st.success(
                                    f"'{next_task.title}' is recurring — next occurrence queued for {next_task.due_date}."
                                )
                            st.rerun()

            st.divider()
            st.subheader("Agentic AI Daily Briefing")
            if assistant is None:
                st.error(f"AI assistant unavailable: {st.session_state['assistant_error']}")
            else:
                briefing_style = st.selectbox(
                    "Briefing style",
                    ["balanced", "calm_coach"],
                    key="briefing_style",
                    help="Specialized style changes tone/format while keeping the same retrieved grounding.",
                )
                if st.button("Generate AI briefing"):
                    st.session_state["ai_daily_brief"] = assistant.generate_daily_briefing(
                        owner=owner,
                        schedule=schedule,
                        style=briefing_style,
                    )
                if "ai_daily_brief" in st.session_state:
                    render_ai_response(st.session_state["ai_daily_brief"])


# ===========================================================================
# Tab 3 — Browse & Filter
# ===========================================================================
with tab_browse:
    st.subheader("Browse & Filter Tasks")
    scheduler = Scheduler(owner)
    pets      = owner.get_pets()

    if not pets:
        st.info("No pets registered yet. Head to Pets & Tasks to get started.")
    else:
        fa, fb = st.columns(2)
        with fa:
            filter_pet    = st.selectbox("Filter by pet",    ["All"] + [p.name for p in pets])
        with fb:
            filter_status = st.selectbox("Filter by status", ["All", "Pending", "Completed"])

        pet_name_arg  = None if filter_pet    == "All" else filter_pet
        completed_arg = None if filter_status == "All" else (filter_status == "Completed")

        results = scheduler.filter_tasks(pet_name=pet_name_arg, completed=completed_arg)

        if results:
            rows = [
                {
                    "Pet":       pn,
                    "Title":     t.title,
                    "Priority":  t.priority,
                    "Duration":  t.duration_minutes,
                    "Frequency": t.frequency,
                    "Required":  "yes" if t.is_required else "no",
                    "Status":    "✓ Done" if t.completed else "Pending",
                }
                for pn, t in results
            ]
            st.dataframe(rows, use_container_width=True)
            st.caption(f"{len(rows)} task(s) shown.")
        else:
            st.info("No tasks match the selected filters.")


# ===========================================================================
# Tab 4 — AI Copilot
# ===========================================================================
with tab_ai:
    st.subheader("Ask the AI Copilot")
    st.caption(
        "This uses an agentic workflow (plan → act → self-check) with retrieval over local pet-care notes."
    )

    if assistant is None:
        st.error(f"AI assistant unavailable: {st.session_state['assistant_error']}")
    else:
        response_style = st.selectbox(
            "Response style",
            ["balanced", "calm_coach"],
            key="copilot_style",
            help="`calm_coach` is a specialized, constrained response format.",
        )
        include_schedule = st.checkbox(
            "Include today's schedule context",
            value=True,
            help="When enabled, the AI uses your generated schedule to personalize advice.",
        )
        question = st.text_area(
            "Your question",
            value="How can I make today's plan safer and easier to maintain?",
            height=100,
        )
        if st.button("Ask AI Copilot", type="primary"):
            context_schedule = st.session_state.get("last_schedule", []) if include_schedule else []
            st.session_state["ai_last_response"] = assistant.answer_question(
                question=question,
                owner=owner,
                schedule=context_schedule,
                style=response_style,
            )

        if "ai_last_response" in st.session_state:
            render_ai_response(st.session_state["ai_last_response"])
