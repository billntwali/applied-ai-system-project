"""
Demo script — run with: python3 main.py
Exercises all scheduler features: sorting, filtering, recurring tasks, conflict detection.
"""

from ai_assistant import PetCareAssistant
from pawpal_system import Owner, Pet, Task, Scheduler, ScheduledTask


def section(title: str) -> None:
    print(f"\n{'=' * 56}")
    print(f"  {title}")
    print(f"{'=' * 56}")


def main():
    # -----------------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------------
    owner = Owner(name="Jordan", day_start="08:00", day_end="20:00")

    mochi = Pet(name="Mochi", species="dog", age=3, breed="Shiba Inu")
    luna  = Pet(name="Luna",  species="cat", age=5)

    # Tasks added OUT OF ORDER intentionally (to demo sort_by_time)
    mochi.add_task(Task(title="Evening walk",   duration_minutes=20, priority="medium", time_of_day="evening"))
    mochi.add_task(Task(title="Morning walk",   duration_minutes=30, priority="high",   time_of_day="morning"))
    mochi.add_task(Task(title="Feed breakfast", duration_minutes=10, priority="high",   frequency="daily"))

    luna.add_task(Task(title="Clean litter box", duration_minutes=10, priority="medium", frequency="daily"))
    luna.add_task(Task(title="Feed breakfast",   duration_minutes=5,  priority="high"))
    luna.add_task(Task(title="Brushing",         duration_minutes=15, priority="low",    is_required=False))

    owner.add_pet(mochi)
    owner.add_pet(luna)

    scheduler = Scheduler(owner)

    # -----------------------------------------------------------------------
    # 1. Base schedule (priority-ordered)
    # -----------------------------------------------------------------------
    section("1. Priority-ordered schedule")
    schedule = scheduler.build_schedule()
    print(scheduler.explain_plan(schedule))

    # -----------------------------------------------------------------------
    # 2. Sorting — same schedule sorted by clock time
    # -----------------------------------------------------------------------
    section("2. Schedule sorted by start time")
    sorted_schedule = scheduler.sort_by_time(schedule)
    for st in sorted_schedule:
        print(f"  {st.start_time} – {st.end_time}  [{st.pet_name}] {st.task.title}")

    # -----------------------------------------------------------------------
    # 3. Filtering
    # -----------------------------------------------------------------------
    section("3a. Filter — only Mochi's tasks")
    for pet_name, task in scheduler.filter_tasks(pet_name="Mochi"):
        status = "✓" if task.completed else "○"
        print(f"  [{status}] {task.title}  ({task.priority}, {task.frequency})")

    section("3b. Filter — incomplete tasks across all pets")
    for pet_name, task in scheduler.filter_tasks(completed=False):
        print(f"  {pet_name}: {task.title}")

    # -----------------------------------------------------------------------
    # 4. Recurring tasks — mark Mochi's daily breakfast complete
    # -----------------------------------------------------------------------
    section("4. Recurring task — complete Mochi's daily breakfast")
    breakfast = next(t for t in mochi.get_tasks() if t.title == "Feed breakfast")
    next_task = scheduler.complete_task(mochi, breakfast)
    print(f"  Marked '{breakfast.title}' complete.  completed={breakfast.completed}")
    if next_task:
        print(f"  Next occurrence auto-added → '{next_task.title}'  due={next_task.due_date}  frequency={next_task.frequency}")

    section("4b. Filter — now show only pending tasks for Mochi")
    for _, task in scheduler.filter_tasks(pet_name="Mochi", completed=False):
        print(f"  ○ {task.title}  (due={task.due_date})")

    # -----------------------------------------------------------------------
    # 5. Conflict detection — manually build overlapping slots to demo
    # -----------------------------------------------------------------------
    section("5. Conflict detection demo")
    walk_task = Task(title="Morning walk",   duration_minutes=30, priority="high")
    feed_task = Task(title="Feed breakfast", duration_minutes=10, priority="high")

    # Deliberately overlapping: both start at 08:00
    conflicting = [
        ScheduledTask(task=walk_task, pet_name="Mochi", start_time="08:00", end_time="08:30"),
        ScheduledTask(task=feed_task, pet_name="Luna",  start_time="08:00", end_time="08:10"),
        ScheduledTask(task=feed_task, pet_name="Mochi", start_time="08:45", end_time="08:55"),
    ]

    conflicts = scheduler.detect_conflicts(conflicting)
    if conflicts:
        for warning in conflicts:
            print(warning)
    else:
        print("  No conflicts found.")

    section("5b. No-conflict schedule (normal build)")
    conflicts = scheduler.detect_conflicts(schedule)
    if conflicts:
        for w in conflicts:
            print(w)
    else:
        print("  No conflicts in the auto-generated schedule.")

    # -----------------------------------------------------------------------
    # 6. Agentic AI workflow (plan -> act -> check)
    # -----------------------------------------------------------------------
    section("6. Agentic AI copilot")
    assistant = PetCareAssistant()
    briefing = assistant.generate_daily_briefing(owner=owner, schedule=schedule)
    print(briefing.answer)
    print("  Workflow trace:")
    for step in briefing.workflow_trace:
        print(f"   - {step}")

    section("6b. Ask a custom AI question")
    answer = assistant.answer_question(
        question="How can I make the plan easier for a busy workday?",
        owner=owner,
        schedule=schedule,
    )
    print(answer.answer)


if __name__ == "__main__":
    main()
