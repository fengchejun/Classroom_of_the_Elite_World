from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class LocationProbability:
    location_id: str
    probability: float  # 0.0 - 1.0


@dataclass
class NPCSchedule:
    char_id: str
    name: str
    current_location: str | None
    weighted_locations: list[LocationProbability]


class Scheduler:
    """Manages NPC location assignment based on probability weights and zone restrictions."""

    def __init__(self):
        # Global zone override: {location_id or "zone_id": [char_id, ...]}
        self._zone_overrides: dict[str, list[str]] = {}

    def set_zone_override(self, zone_or_location: str, char_ids: list[str]) -> None:
        """Force specific characters into a zone/location, overriding their schedules."""
        self._zone_overrides[zone_or_location] = char_ids

    def clear_zone_overrides(self) -> None:
        self._zone_overrides.clear()

    def clear_override_for(self, zone_or_location: str) -> None:
        self._zone_overrides.pop(zone_or_location, None)

    def get_npc_location(
        self,
        char_id: str,
        name: str,
        time_slot: str,
        day_of_week: int,
        is_weekend: bool,
        schedule_weights: dict | None,
        default_location: str = "classroom_d",
    ) -> str:
        """
        Determine NPC's current location.
        1. Check zone overrides first.
        2. Fall back to schedule weights for this time slot.
        3. Fall back to default location.
        """
        # Check all zone overrides
        for zone, chars in self._zone_overrides.items():
            if char_id in chars:
                return zone

        # Use schedule weights
        if schedule_weights:
            slot_key = "weekend" if (is_weekend and "weekend" in schedule_weights) else time_slot
            weights = schedule_weights.get(slot_key, schedule_weights.get("default", {}))
            if weights:
                return self._weighted_random(weights)

        return default_location

    def get_visible_npcs(
        self,
        target_location: str,
        all_characters: list[dict],
        time_slot: str,
        day_of_week: int,
        is_weekend: bool,
    ) -> list[dict]:
        """
        Returns list of characters currently at a given location.
        Each char dict: {char_id, name, schedule_weights, status_tags, class_name}
        """
        present = []
        for char in all_characters:
            loc = self.get_npc_location(
                char_id=char["char_id"],
                name=char["name"],
                time_slot=time_slot,
                day_of_week=day_of_week,
                is_weekend=is_weekend,
                schedule_weights=char.get("schedule_weights"),
                default_location=char.get("default_location", "classroom_d"),
            )
            if loc == target_location:
                present.append(char)
        return present

    @staticmethod
    def _weighted_random(weights: dict[str, float]) -> str:
        """Pick a location key based on probability weights."""
        locations = list(weights.keys())
        probs = list(weights.values())
        total = sum(probs)
        if total <= 0:
            return locations[0] if locations else "classroom_d"
        probs = [p / total for p in probs]
        return random.choices(locations, weights=probs, k=1)[0]
