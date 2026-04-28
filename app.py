import streamlit as st
from ai_assistant import AIResponse, PetCareAssistant
from pawpal_system import Owner, Pet, Task, Scheduler

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="wide")

SPECIES_EMOJI = {"dog": "🐕", "cat": "🐱", "rabbit": "🐰", "bird": "🐦", "other": "🐾"}
PRIORITY_ICON = {"high": "🔴", "medium": "🟡", "low": "🟢"}


def clear_cached_outputs() -> None:
    for key in ("last_schedule", "ai_daily_brief", "ai_last_response"):
        st.session_state.pop(key, None)


def render_ai_response(response: AIResponse) -> None:
    if response.guardrail_triggered:
        st.warning(response.answer)
        return

    st.markdown(response.answer)
    st.divider()

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Confidence", f"{int(response.confidence * 100)}%")
    with c2:
        st.metric("Sources consulted", len(response.sources))
    with c3:
        mode_label = "AI-powered" if "llm" in response.mode else "Local knowledge"
        st.metric("Answer mode", mode_label)

    if response.sources:
        with st.expander("Sources used", expanded=False):
            for item in response.sources:
                st.markdown(f"- **{item.title}** — _{item.source}_")

    with st.expander("How this answer was generated", expanded=False):
        for step in response.workflow_trace:
            st.write(f"- {step}")

    with st.expander("Reasoning steps", expanded=False):
        rows = [{"Step": s.name, "Observation": s.observation} for s in response.steps]
        st.table(rows)


# ---------------------------------------------------------------------------
# Session state
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
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Owner Settings")
    new_name  = st.text_input("Your name",          value=owner.name)
    new_start = st.text_input("Day start (HH:MM)",  value=owner.day_start)
    new_end   = st.text_input("Day end   (HH:MM)",  value=owner.day_end)
    if st.button("Save settings"):
        owner.name      = new_name
        owner.day_start = new_start
        owner.day_end   = new_end
        clear_cached_outputs()
        st.success(f"Saved for {owner.name}.")

    st.divider()

    pets = owner.get_pets()
    total_tasks = sum(len(p.get_tasks()) for p in pets)
    done_tasks  = sum(1 for p in pets for t in p.get_tasks() if t.completed)

    st.markdown(f"**{len(pets)}** pet{'s' if len(pets) != 1 else ''} · "
                f"**{total_tasks}** task{'s' if total_tasks != 1 else ''}")
    if total_tasks:
        st.progress(done_tasks / total_tasks,
                    text=f"{done_tasks}/{total_tasks} completed today")

    st.divider()
    st.caption("🐾 PawPal+ · Daily Pet Care Planner")


# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------
st.title("🐾 PawPal+")
st.caption("Smart daily care planner for your pets.")

if not owner.get_pets():
    st.info("Welcome! Head to **Pets & Tasks** to add your first pet and get started.")

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
        add_pet_btn = st.form_submit_button("Add Pet", use_container_width=True)

    if add_pet_btn and pet_name.strip():
        owner.add_pet(Pet(
            name=pet_name.strip(), species=species,
            age=int(age), breed=breed.strip(),
        ))
        clear_cached_outputs()
        st.success(f"{SPECIES_EMOJI.get(species, '🐾')} {pet_name.strip()} added!")
        st.rerun()

    pets = owner.get_pets()
    if not pets:
        st.info("No pets yet — add one above to get started.")
    else:
        for pet in pets:
            emoji = SPECIES_EMOJI.get(pet.species, "🐾")
            tasks = pet.get_tasks()
            done  = sum(1 for t in tasks if t.completed)

            with st.container(border=True):
                header_col, delete_col = st.columns([5, 1])
                with header_col:
                    label = f"{emoji} **{pet.name}** — {pet.species}, age {pet.age}"
                    if pet.breed:
                        label += f", {pet.breed}"
                    if tasks:
                        label += f"  ·  {done}/{len(tasks)} tasks done"
                    st.markdown(label)
                with delete_col:
                    if st.button("Remove", key=f"del_pet_{pet.name}",
                                 help=f"Remove {pet.name} and all their tasks"):
                        owner.remove_pet(pet.name)
                        clear_cached_outputs()
                        st.rerun()

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
            add_task_btn = st.form_submit_button("Add Task", use_container_width=True)

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
            st.rerun()

        # Task lists per pet
        for pet in pets:
            tasks = pet.get_tasks()
            if tasks:
                done = sum(1 for t in tasks if t.completed)
                with st.expander(
                    f"{SPECIES_EMOJI.get(pet.species, '🐾')} {pet.name}'s tasks "
                    f"({done}/{len(tasks)} done)",
                    expanded=False,
                ):
                    for task in tasks:
                        row_col, del_col = st.columns([6, 1])
                        with row_col:
                            icon   = PRIORITY_ICON.get(task.priority, "")
                            status = "✅" if task.completed else "🔲"
                            freq   = f" · `{task.frequency}`" if task.frequency != "once" else ""
                            req    = "" if task.is_required else " · _optional_"
                            st.markdown(
                                f"{status} {icon} **{task.title}** "
                                f"({task.duration_minutes} min, {task.priority}){freq}{req}"
                            )
                        with del_col:
                            if st.button("✕", key=f"del_task_{pet.name}_{task.title}",
                                         help="Delete this task"):
                                pet.remove_task(task)
                                clear_cached_outputs()
                                st.rerun()


# ===========================================================================
# Tab 2 — Today's Schedule
# ===========================================================================
with tab_schedule:
    st.subheader("Today's Schedule")
    scheduler = Scheduler(owner)

    col_gen, col_clear = st.columns([2, 1])
    with col_gen:
        if st.button("Generate schedule", type="primary", use_container_width=True):
            all_tasks = [t for p in owner.get_pets() for t in p.get_tasks()]
            if not all_tasks:
                st.warning("Add at least one task before generating a schedule.")
            else:
                st.session_state["last_schedule"] = scheduler.build_schedule()
    with col_clear:
        if "last_schedule" in st.session_state:
            if st.button("Clear schedule", use_container_width=True):
                st.session_state.pop("last_schedule", None)
                st.rerun()

    if "last_schedule" in st.session_state:
        schedule = st.session_state["last_schedule"]

        if not schedule:
            st.info("No tasks to schedule — all may already be completed, or none fit the time window.")
        else:
            # Progress bar
            done_count  = sum(1 for e in schedule if e.task.completed)
            total_count = len(schedule)
            st.progress(done_count / total_count,
                        text=f"{done_count}/{total_count} tasks completed")

            # Conflicts
            conflicts = scheduler.detect_conflicts(schedule)
            if conflicts:
                for w in conflicts:
                    st.warning(w)
            else:
                st.success(
                    f"{total_count} task(s) scheduled between "
                    f"{owner.day_start} and {owner.day_end} — no conflicts detected."
                )

            # Sort toggle
            sort_order = st.radio(
                "Display order", ["Priority order", "Chronological"], horizontal=True
            )
            display = scheduler.sort_by_time(schedule) if sort_order == "Chronological" else schedule

            st.divider()

            for i, entry in enumerate(display):
                priority_icon = PRIORITY_ICON.get(entry.task.priority, "")
                status_icon   = "✅" if entry.task.completed else "🔲"
                freq_badge    = f"  `{entry.task.frequency}`" if entry.task.frequency != "once" else ""

                with st.container(border=True):
                    info_col, btn_col = st.columns([6, 1])
                    with info_col:
                        st.markdown(
                            f"{status_icon} {priority_icon} "
                            f"**{entry.start_time} – {entry.end_time}** &nbsp;|&nbsp; "
                            f"**{entry.pet_name}**: {entry.task.title} "
                            f"({entry.task.duration_minutes} min){freq_badge}"
                        )
                        st.caption(entry.reason)
                    with btn_col:
                        if not entry.task.completed:
                            if st.button("Done ✓", key=f"done_{i}", use_container_width=True):
                                target_pet = next(
                                    p for p in owner.get_pets() if p.name == entry.pet_name
                                )
                                next_task = scheduler.complete_task(target_pet, entry.task)
                                clear_cached_outputs()
                                if next_task:
                                    st.success(
                                        f"'{next_task.title}' is recurring — "
                                        f"next occurrence queued for {next_task.due_date}."
                                    )
                                st.rerun()

            st.divider()
            st.subheader("AI Daily Briefing")
            if assistant is None:
                st.error(f"AI assistant unavailable: {st.session_state['assistant_error']}")
            else:
                briefing_style = st.selectbox(
                    "Briefing style",
                    ["balanced", "calm_coach"],
                    key="briefing_style",
                    help="`calm_coach` uses a structured, supportive format.",
                )
                if st.button("Generate briefing", use_container_width=True):
                    with st.spinner("Generating your briefing..."):
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
        st.info("No pets registered yet. Head to **Pets & Tasks** to get started.")
    else:
        fa, fb, fc = st.columns(3)
        with fa:
            filter_pet      = st.selectbox("Filter by pet",      ["All"] + [p.name for p in pets])
        with fb:
            filter_status   = st.selectbox("Filter by status",   ["All", "Pending", "Completed"])
        with fc:
            filter_priority = st.selectbox("Filter by priority", ["All", "high", "medium", "low"])

        pet_name_arg  = None if filter_pet    == "All" else filter_pet
        completed_arg = None if filter_status == "All" else (filter_status == "Completed")

        results = scheduler.filter_tasks(pet_name=pet_name_arg, completed=completed_arg)

        if filter_priority != "All":
            results = [(pn, t) for pn, t in results if t.priority == filter_priority]

        if results:
            rows = [
                {
                    "Pet":       pn,
                    "Title":     t.title,
                    "Priority":  f"{PRIORITY_ICON.get(t.priority, '')} {t.priority}",
                    "Duration":  f"{t.duration_minutes} min",
                    "Frequency": t.frequency,
                    "Required":  "yes" if t.is_required else "no",
                    "Status":    "✅ Done" if t.completed else "🔲 Pending",
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
        "Answers are grounded in retrieved pet-care notes and your schedule. "
        "The AI plans, retrieves, drafts, then self-checks its response."
    )

    if assistant is None:
        st.error(f"AI assistant unavailable: {st.session_state['assistant_error']}")
    else:
        ca, cb = st.columns([1, 1])
        with ca:
            response_style = st.selectbox(
                "Response style",
                ["balanced", "calm_coach"],
                key="copilot_style",
                help="`calm_coach` uses a structured, supportive format.",
            )
        with cb:
            include_schedule = st.checkbox(
                "Include today's schedule context",
                value=True,
                help="The AI uses your generated schedule to personalize advice.",
            )

        question = st.text_area(
            "Your question",
            value="How can I make today's plan safer and easier to maintain?",
            height=100,
        )

        if st.button("Ask AI Copilot", type="primary", use_container_width=True):
            if not question.strip():
                st.warning("Please enter a question.")
            else:
                context_schedule = st.session_state.get("last_schedule", []) if include_schedule else []
                with st.spinner("Thinking..."):
                    st.session_state["ai_last_response"] = assistant.answer_question(
                        question=question,
                        owner=owner,
                        schedule=context_schedule,
                        style=response_style,
                    )

        if "ai_last_response" in st.session_state:
            render_ai_response(st.session_state["ai_last_response"])
