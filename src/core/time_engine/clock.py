from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

TIME_SLOTS = ["morning", "noon", "dusk", "evening", "late_night"]
SLOT_HOURS = {
    "morning": range(6, 12),
    "noon": range(12, 17),
    "dusk": range(17, 19),
    "evening": range(19, 22),
    "late_night": range(22, 24),
}


@dataclass(frozen=True)
class TimeState:
    game_date: str       # "YYYY-MM-DD"
    time_slot: str        # morning | noon | dusk | evening | late_night

    @property
    def date_obj(self) -> datetime:
        return datetime.strptime(self.game_date, "%Y-%m-%d")

    @property
    def slot_index(self) -> int:
        return TIME_SLOTS.index(self.time_slot)

    def to_dict(self) -> dict:
        return {"game_date": self.game_date, "time_slot": self.time_slot}


class Clock:
    """Manages game time progression with absolute date + time-slot tracking."""

    def __init__(self, initial_date: str = "2024-04-01", initial_slot: str = "morning"):
        self._date_str = initial_date
        self._slot = initial_slot

    @property
    def now(self) -> TimeState:
        return TimeState(game_date=self._date_str, time_slot=self._slot)

    def advance(self, slots: int = 1) -> TimeState:
        """Advance by N time slots, crossing date boundaries as needed."""
        current_idx = TIME_SLOTS.index(self._slot)
        total_slots = len(TIME_SLOTS)

        new_idx = current_idx + slots
        days_passed = new_idx // total_slots
        remainder = new_idx % total_slots

        if days_passed > 0:
            dt = datetime.strptime(self._date_str, "%Y-%m-%d") + timedelta(days=days_passed)
            self._date_str = dt.strftime("%Y-%m-%d")

        self._slot = TIME_SLOTS[remainder]
        return self.now

    def advance_to_slot(self, target_slot: str) -> TimeState:
        """Advance to a specific time slot. If target is earlier in the day, cross to next day."""
        target_idx = TIME_SLOTS.index(target_slot)
        current_idx = TIME_SLOTS.index(self._slot)

        if target_idx > current_idx:
            return self.advance(target_idx - current_idx)
        elif target_idx < current_idx:
            # Cross to next day
            return self.advance(len(TIME_SLOTS) - current_idx + target_idx)
        return self.now  # Already at target

    def advance_day(self, days: int = 1) -> TimeState:
        """Advance by N full days, keeping same time slot."""
        dt = datetime.strptime(self._date_str, "%Y-%m-%d") + timedelta(days=days)
        self._date_str = dt.strftime("%Y-%m-%d")
        return self.now

    def set_time(self, date_str: str, slot: str) -> None:
        """Directly set time (for GM/debug). Validates inputs."""
        datetime.strptime(date_str, "%Y-%m-%d")  # validate format
        if slot not in TIME_SLOTS:
            raise ValueError(f"Invalid time slot: {slot}. Must be one of {TIME_SLOTS}")
        self._date_str = date_str
        self._slot = slot

    def is_weekend(self) -> bool:
        dt = datetime.strptime(self._date_str, "%Y-%m-%d")
        return dt.weekday() >= 5  # Saturday=5, Sunday=6

    def day_of_week(self) -> int:
        """0=Monday, 6=Sunday"""
        return datetime.strptime(self._date_str, "%Y-%m-%d").weekday()

    def days_until(self, target_date: str) -> int:
        """Days remaining until a target date (negative if past)."""
        current = datetime.strptime(self._date_str, "%Y-%m-%d")
        target = datetime.strptime(target_date, "%Y-%m-%d")
        return (target - current).days

    def slots_until(self, target_date: str, target_slot: str) -> int:
        """Total time slots between now and a target date+slot."""
        days = self.days_until(target_date)
        target_idx = TIME_SLOTS.index(target_slot)
        current_idx = TIME_SLOTS.index(self._slot)
        if days == 0:
            return max(0, target_idx - current_idx)
        return days * len(TIME_SLOTS) + target_idx - current_idx
