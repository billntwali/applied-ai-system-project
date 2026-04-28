"""
PawPal+ — backend logic layer.
All classes representing the domain model and scheduling live here.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import Optional


PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


# ---------------------------------------------------------------------------
# Data-only objects (dataclasses)
# ---------------------------------------------------------------------------

@dataclass
class Task:
    """A single pet-care activity that can be scheduled."""
    title: str
    duration_minutes: int
    priority: str                      # "low" | "medium" | "high"
    time_of_day: Optional[str] = None  # "morning" | "afternoon" | "evening" | None
    is_required: bool = True
    completed: bool = False
    frequency: str = "once"            # "once" | "daily" | "weekly"
    due_date: Optional[date] = None    # date this task is due (None = today)

    def mark_complete(self) -> Optional["Task"]:
        """Mark this task done; return a new Task for the next occurrence if recurring."""
        self.completed = True
        if self.frequency == "once":
            return None
        base = self.due_date if self.due_date is not None else date.today()
        delta = timedelta(days=1) if self.frequency == "daily" else timedelta(weeks=1)
        return Task(
            title=self.title,
            duration_minutes=self.duration_minutes,
            priority=self.priority,
            time_of_day=self.time_of_day,
            is_required=self.is_required,
            completed=False,
            frequency=self.frequency,
            due_date=base + delta,
        )


@dataclass
class ScheduledTask:
    """A Task that has been placed on the day's timeline."""
    task: Task
    pet_name: str          # which pet this task is for
    start_time: str        # e.g. "08:00"
    end_time: str          # e.g. "08:20"
    reason: str = ""       # why this task was chosen / placed here


# ---------------------------------------------------------------------------
# Domain objects
# ---------------------------------------------------------------------------

class Pet:
    """Represents a pet owned by an Owner."""

    def __init__(
        self,
        name: str,
        species: str,
        age: int,
        breed: str = "",
        special_needs: Optional[list[str]] = None,
    ) -> None:
        self.name = name
        self.species = species
        self.age = age
        self.breed = breed
        self.special_needs: list[str] = special_needs or []
        self._tasks: list[Task] = []

    def add_task(self, task: Task) -> None:
        """Attach a care task to this pet."""
        self._tasks.append(task)

    def get_tasks(self) -> list[Task]:
        """Return a copy of all tasks associated with this pet."""
        return list(self._tasks)

    def remove_task(self, task: Task) -> None:
        """Remove a specific task from this pet."""
        self._tasks = [t for t in self._tasks if t is not task]


class Owner:
    """Represents the pet owner and their daily availability."""

    def __init__(
        self,
        name: str,
        email: str = "",
        day_start: str = "07:00",
        day_end: str = "21:00",
    ) -> None:
        self.name = name
        self.email = email
        self.day_start = day_start  # earliest time owner is available
        self.day_end = day_end      # latest time owner is available
        self._pets: list[Pet] = []

    def add_pet(self, pet: Pet) -> None:
        """Register a pet under this owner."""
        self._pets.append(pet)

    def remove_pet(self, pet_name: str) -> None:
        """Remove a pet by name."""
        self._pets = [p for p in self._pets if p.name != pet_name]

    def get_pets(self) -> list[Pet]:
        """Return a copy of all pets owned by this owner."""
        return list(self._pets)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class Scheduler:
    """Builds a prioritised daily care schedule for all of an owner's pets."""

    def __init__(self, owner: Owner) -> None:
        self.owner = owner

    # --- core scheduling ---------------------------------------------------

    def prioritize_tasks(self, tasks: list[tuple]) -> list[tuple]:
        """Sort (task, pet_name) pairs: required first, then high → medium → low priority."""
        return sorted(
            tasks,
            key=lambda pair: (
                0 if pair[0].is_required else 1,
                PRIORITY_ORDER.get(pair[0].priority, 2),
            ),
        )

    def build_schedule(self) -> list[ScheduledTask]:
        """Fit prioritised tasks into the owner's available time window and return the plan."""
        all_tasks: list[tuple] = []
        for pet in self.owner.get_pets():
            for task in pet.get_tasks():
                if not task.completed:
                    all_tasks.append((task, pet.name))

        ordered = self.prioritize_tasks(all_tasks)

        schedule: list[ScheduledTask] = []
        current = datetime.strptime(self.owner.day_start, "%H:%M")
        day_end = datetime.strptime(self.owner.day_end, "%H:%M")

        for task, pet_name in ordered:
            end = current + timedelta(minutes=task.duration_minutes)
            if end > day_end:
                continue  # skip tasks that won't fit; try smaller ones
            schedule.append(ScheduledTask(
                task=task,
                pet_name=pet_name,
                start_time=current.strftime("%H:%M"),
                end_time=end.strftime("%H:%M"),
                reason=self._make_reason(task, pet_name),
            ))
            current = end

        return schedule

    def _make_reason(self, task: Task, pet_name: str) -> str:
        """Build a plain-English reason string for a scheduled task."""
        required_label = "required" if task.is_required else "optional"
        freq_label = f" ({task.frequency})" if task.frequency != "once" else ""
        return f"{task.priority.capitalize()}-priority {required_label}{freq_label} task for {pet_name}."

    def explain_plan(self, schedule: list[ScheduledTask]) -> str:
        """Return a human-readable summary of the full schedule."""
        if not schedule:
            return "No tasks could be scheduled within the available time window."

        lines = [f"Today's Schedule for {self.owner.name}'s pets", "=" * 56]
        for st in schedule:
            status = "✓" if st.task.completed else " "
            lines.append(
                f"[{status}] {st.start_time} – {st.end_time}  "
                f"{st.pet_name}: {st.task.title}  "
                f"({st.task.duration_minutes} min)  |  {st.reason}"
            )
        lines.append("=" * 56)
        lines.append(f"Total tasks: {len(schedule)}")
        return "\n".join(lines)

    # --- Step 2: Sorting and Filtering ------------------------------------

    def sort_by_time(self, schedule: list[ScheduledTask]) -> list[ScheduledTask]:
        """Return the schedule sorted by start_time ascending (HH:MM strings sort correctly)."""
        return sorted(schedule, key=lambda st: st.start_time)

    def filter_tasks(
        self,
        pet_name: Optional[str] = None,
        completed: Optional[bool] = None,
    ) -> list[tuple[str, Task]]:
        """
        Return (pet_name, task) pairs across all pets, optionally filtered by
        pet name and/or completion status.
        """
        results: list[tuple[str, Task]] = []
        for pet in self.owner.get_pets():
            if pet_name is not None and pet.name != pet_name:
                continue
            for task in pet.get_tasks():
                if completed is not None and task.completed != completed:
                    continue
                results.append((pet.name, task))
        return results

    # --- Step 3: Recurring tasks ------------------------------------------

    def complete_task(self, pet: Pet, task: Task) -> Optional[Task]:
        """
        Mark a task complete. If it is recurring, automatically add the next
        occurrence to the pet and return it; otherwise return None.
        """
        next_task = task.mark_complete()
        if next_task is not None:
            pet.add_task(next_task)
        return next_task

    # --- Step 4: Conflict detection ---------------------------------------

    def detect_conflicts(self, schedule: list[ScheduledTask]) -> list[str]:
        """
        Check every pair of scheduled tasks for overlapping time windows.
        Returns a list of human-readable warning strings (empty if no conflicts).

        Two tasks conflict when: A.start < B.end AND B.start < A.end
        """
        warnings: list[str] = []
        for i, a in enumerate(schedule):
            for b in schedule[i + 1:]:
                if a.start_time < b.end_time and b.start_time < a.end_time:
                    warnings.append(
                        f"WARNING — Conflict detected:\n"
                        f"  [{a.pet_name}] {a.task.title}  {a.start_time}–{a.end_time}\n"
                        f"  [{b.pet_name}] {b.task.title}  {b.start_time}–{b.end_time}"
                    )
        return warnings
