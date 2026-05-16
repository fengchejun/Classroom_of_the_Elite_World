from __future__ import annotations

from dataclasses import dataclass, field

from src.models.event import Event


@dataclass
class TriggerMatch:
    event: Event
    match_type: str  # "exact" | "date_only" | "location_only" | "prerequisite"
    priority: int = 0


class TriggerEngine:
    """Evaluates event trigger conditions against current game state."""

    async def check(
        self,
        events: list[Event],
        game_date: str,
        time_slot: str,
        location_id: str,
        completed_events: set[str],
        player_char_id: str | None = None,
    ) -> list[TriggerMatch]:
        """
        Check all pending events for trigger matches.
        Returns sorted by priority (highest first).
        """
        matches = []

        for event in events:
            if not event.is_active and event.phase.value == "pending":
                match = self._evaluate(
                    event, game_date, time_slot, location_id,
                    completed_events, player_char_id,
                )
                if match:
                    matches.append(match)

        # Sort: higher priority first, then exact matches before partial
        matches.sort(key=lambda m: (m.priority, 0 if m.match_type == "exact" else 1), reverse=True)
        return matches

    def _evaluate(
        self,
        event: Event,
        game_date: str,
        time_slot: str,
        location_id: str,
        completed_events: set[str],
        player_char_id: str | None = None,
    ) -> TriggerMatch | None:
        """Evaluate a single event's trigger conditions."""

        # Check prerequisite events
        prerequisites = event.prerequisite_events or []
        for prereq in prerequisites:
            if prereq not in completed_events:
                return None

        # Check player character requirement
        if event.required_player_char and event.required_player_char != player_char_id:
            return None

        date_match = False
        location_match = False
        slot_match = False

        # Check date
        if event.required_date:
            if event.required_date == game_date:
                date_match = True
        else:
            date_match = True  # No date requirement = always matches

        # Check time slot
        if event.required_time_slot:
            if event.required_time_slot == time_slot:
                slot_match = True
        else:
            slot_match = True

        # Check location
        if event.required_location:
            if event.required_location == location_id:
                location_match = True
        else:
            location_match = True

        # Character match bonus
        char_bonus = 2 if (event.required_player_char and event.required_player_char == player_char_id) else 0

        # Determine match type
        if date_match and location_match and slot_match:
            return TriggerMatch(event=event, match_type="exact", priority=10 + char_bonus)
        elif date_match and slot_match:
            return TriggerMatch(event=event, match_type="date_only", priority=5 + char_bonus)
        elif location_match and slot_match:
            return TriggerMatch(event=event, match_type="location_only", priority=3 + char_bonus)
        elif date_match:
            return TriggerMatch(event=event, match_type="date_only", priority=2 + char_bonus)

        return None
