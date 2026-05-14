from __future__ import annotations

import pytest

from src.core.time_engine.clock import TIME_SLOTS, Clock, TimeState
from src.core.time_engine.scheduler import Scheduler
from src.core.time_engine.spotlight import Spotlight, SpotlightNPC


class TestClock:
    def test_initial_state(self):
        clock = Clock()
        assert clock.now == TimeState(game_date="2024-04-01", time_slot="morning")

    def test_advance_single_slot(self):
        clock = Clock()
        clock.advance(1)
        assert clock.now.time_slot == "noon"
        assert clock.now.game_date == "2024-04-01"

    def test_advance_cross_day(self):
        clock = Clock(initial_slot="late_night")
        clock.advance(1)
        assert clock.now.time_slot == "morning"
        assert clock.now.game_date == "2024-04-02"

    def test_advance_cross_month(self):
        clock = Clock(initial_date="2024-04-30", initial_slot="late_night")
        clock.advance(1)
        assert clock.now.game_date == "2024-05-01"
        assert clock.now.time_slot == "morning"

    def test_advance_multiple_slots_cross_day(self):
        clock = Clock(initial_slot="noon")
        clock.advance(4)  # noon->dusk->evening->late_night->morning(next day)
        assert clock.now.time_slot == "morning"
        assert clock.now.game_date == "2024-04-02"

    def test_advance_to_slot_same_day(self):
        clock = Clock(initial_slot="morning")
        clock.advance_to_slot("evening")
        assert clock.now.time_slot == "evening"
        assert clock.now.game_date == "2024-04-01"

    def test_advance_to_slot_next_day(self):
        clock = Clock(initial_slot="evening")
        clock.advance_to_slot("morning")
        assert clock.now.time_slot == "morning"
        assert clock.now.game_date == "2024-04-02"

    def test_set_time(self):
        clock = Clock()
        clock.set_time("2024-08-01", "noon")
        assert clock.now == TimeState(game_date="2024-08-01", time_slot="noon")

    def test_set_time_invalid_slot(self):
        clock = Clock()
        with pytest.raises(ValueError):
            clock.set_time("2024-04-01", "midnight")

    def test_is_weekend(self):
        clock = Clock(initial_date="2024-04-06")  # Saturday
        assert clock.is_weekend()
        clock.set_time("2024-04-07", "morning")  # Sunday
        assert clock.is_weekend()
        clock.set_time("2024-04-08", "morning")  # Monday
        assert not clock.is_weekend()

    def test_days_until(self):
        clock = Clock(initial_date="2024-04-01")
        assert clock.days_until("2024-04-10") == 9
        assert clock.days_until("2024-03-30") == -2

    def test_slots_until(self):
        clock = Clock(initial_date="2024-04-01", initial_slot="morning")
        # morning->noon = 1 slot
        assert clock.slots_until("2024-04-01", "noon") == 1
        # morning to next day morning = 5 slots (full day rotation)
        assert clock.slots_until("2024-04-02", "morning") == 5

    def test_time_state_to_dict(self):
        state = TimeState(game_date="2024-04-01", time_slot="morning")
        assert state.to_dict() == {"game_date": "2024-04-01", "time_slot": "morning"}

    def test_full_day_cycle(self):
        clock = Clock()
        states = []
        for _ in range(5):
            states.append((clock.now.game_date, clock.now.time_slot))
            clock.advance(1)
        expected = [
            ("2024-04-01", "morning"),
            ("2024-04-01", "noon"),
            ("2024-04-01", "dusk"),
            ("2024-04-01", "evening"),
            ("2024-04-01", "late_night"),
        ]
        assert states == expected
        assert clock.now.game_date == "2024-04-02"
        assert clock.now.time_slot == "morning"


class TestScheduler:
    def test_weighted_random_deterministic(self):
        scheduler = Scheduler()
        # With 100% probability to one item, should always pick it
        result = scheduler._weighted_random({"gym": 1.0, "classroom": 0.0})
        assert result == "gym"

    def test_npc_location_schedule_weights(self):
        scheduler = Scheduler()
        weights = {"noon": {"cafeteria": 1.0, "classroom": 0.0}}
        loc = scheduler.get_npc_location(
            char_id="c1", name="Test", time_slot="noon",
            day_of_week=2, is_weekend=False,
            schedule_weights=weights,
        )
        assert loc == "cafeteria"

    def test_zone_override_has_priority(self):
        scheduler = Scheduler()
        scheduler.set_zone_override("island_beach", ["c1", "c2"])
        weights = {"noon": {"classroom": 1.0}}
        loc = scheduler.get_npc_location(
            char_id="c1", name="Test", time_slot="noon",
            day_of_week=2, is_weekend=False,
            schedule_weights=weights,
        )
        assert loc == "island_beach"

    def test_default_location_fallback(self):
        scheduler = Scheduler()
        loc = scheduler.get_npc_location(
            char_id="c1", name="Test", time_slot="noon",
            day_of_week=2, is_weekend=False,
            schedule_weights=None,
            default_location="classroom_d",
        )
        assert loc == "classroom_d"

    def test_clear_zone_overrides(self):
        scheduler = Scheduler()
        scheduler.set_zone_override("beach", ["c1"])
        scheduler.clear_zone_overrides()
        assert len(scheduler._zone_overrides) == 0


class TestSpotlight:
    def _make_npc(self, char_id, name="TestNPC", tags=None):
        return {"char_id": char_id, "name": name, "status_tags": tags or ["normal"]}

    def test_empty_present_npcs(self):
        spotlight = Spotlight(max_npcs=3)
        result = spotlight.select([])
        assert result == []

    def test_selects_up_to_max(self):
        spotlight = Spotlight(max_npcs=3)
        npcs = [self._make_npc(f"c{i}") for i in range(5)]
        result = spotlight.select(npcs)
        assert 0 < len(result) <= 3

    def test_force_include(self):
        spotlight = Spotlight(max_npcs=3)
        npcs = [self._make_npc(f"c{i}") for i in range(5)]
        result = spotlight.select(npcs, force_include=["c0"])
        assert any(n.char_id == "c0" for n in result)

    def test_critical_priority(self):
        spotlight = Spotlight(max_npcs=3)
        npcs = [self._make_npc(f"c{i}") for i in range(5)]
        result = spotlight.select(npcs, critical_char_ids={"c4"})
        # c4 should be in result if slots available
        assert any(n.char_id == "c4" for n in result)

    def test_excludes_player(self):
        spotlight = Spotlight(max_npcs=3)
        npcs = [self._make_npc("player"), self._make_npc("c1")]
        result = spotlight.select(npcs, player_char_id="player")
        assert not any(n.char_id == "player" for n in result)

    def test_spotlight_status_from_tags(self):
        spotlight = Spotlight(max_npcs=1)
        npcs = [self._make_npc("c1", tags=["reading"])]
        result = spotlight.select(npcs)
        assert result[0].brief_status == "正在读书"
