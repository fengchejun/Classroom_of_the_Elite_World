from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.event_bus.lifecycle import LifecycleAdvancement, LifecycleManager
from src.core.event_bus.rulebook import RulebookManager
from src.core.event_bus.triggers import TriggerEngine, TriggerMatch
from src.models.event import DynamicEvent, Event, EventPhase, EventType
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class EventContext:
    """The context returned when an event fires, ready for prompt injection."""
    event_id: str
    event_name: str
    event_type: str
    phase: str
    ai_prompt: str | None        # Inject into LLM system prompt
    options: list[dict] | None   # For ai_guided_choice events
    rules_appendix: str | None   # Rulebook content for LLM
    silent_effects: dict | None  # For silent_fixed events


@dataclass
class ChoiceResolution:
    """Result of a player's choice selection."""
    narrative_hook: str          # LLM prompt to continue narration
    stat_changes: dict           # e.g. {"sudo_affection": -2}
    target_event_id: str | None  # Next event to trigger, if any


class EventBus:
    """
    Dual-track event bus. Loads static events from config,
    manages dynamic events from forecaster, and controls lifecycle.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.trigger_engine = TriggerEngine()
        self.lifecycle = LifecycleManager()
        self.rulebook = RulebookManager()
        self._completed_events: set[str] = set()

    # ---- Event Loading ----

    async def load_from_config(self, config_path: str | None = None) -> int:
        """Load event definitions from events_config.json into the database."""
        if config_path is None:
            config_path = str(
                Path(__file__).parent.parent.parent
                / "config" / "data" / "events_config.json"
            )

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        count = 0
        for event_id, definition in config.items():
            event = await self._upsert_event(event_id, definition)
            count += 1

        await self.session.flush()
        logger.info(f"Loaded {count} events from config")
        return count

    async def _upsert_event(self, event_id: str, definition: dict) -> Event:
        result = await self.session.execute(
            select(Event).where(Event.template_id == event_id)
        )
        event = result.scalar_one_or_none()

        trigger = definition.get("trigger_conditions", {})

        kwargs = {
            "template_id": event_id,
            "name": definition.get("name", event_id),
            "event_type": EventType(definition.get("type", "fixed_story")),
            "required_date": trigger.get("required_date"),
            "required_time_slot": trigger.get("required_time_slot"),
            "required_location": trigger.get("required_location"),
            "prerequisite_events": trigger.get("prerequisite_events"),
            "foreshadow_start_date": definition.get("foreshadow_start_date"),
            "foreshadow_probability": definition.get("foreshadow_probability", 0.3),
            "foreshadow_prompt": definition.get("foreshadow_prompt"),
            "transition_date": definition.get("transition_date"),
            "active_start_date": definition.get("active_start_date"),
            "active_end_date": definition.get("active_end_date"),
            "ai_setup_prompt": definition.get("ai_setup_prompt"),
            "active_prompt": definition.get("active_prompt"),
            "options": definition.get("options"),
            "rules_appendix": definition.get("rules_appendix"),
            "silent_effects": definition.get("silent_effects"),
        }

        if event:
            for key, value in kwargs.items():
                setattr(event, key, value)
        else:
            event = Event(**kwargs)
            self.session.add(event)

        return event

    # ---- Trigger Checking ----

    async def check_triggers(
        self, location_id: str, game_date: str, time_slot: str
    ) -> list[TriggerMatch]:
        """Check for event triggers at the current location and time."""
        result = await self.session.execute(
            select(Event).where(Event.is_active == False)
        )
        events = result.scalars().all()

        matches = await self.trigger_engine.check(
            events=list(events),
            game_date=game_date,
            time_slot=time_slot,
            location_id=location_id,
            completed_events=self._completed_events,
        )
        return matches

    async def check_dynamic_triggers(
        self, location_id: str, game_date: str
    ) -> list[DynamicEvent]:
        """Check for AI-generated dynamic events at this location."""
        result = await self.session.execute(
            select(DynamicEvent).where(
                DynamicEvent.is_triggered == False,
                DynamicEvent.is_expired == False,
                DynamicEvent.trigger_location == location_id,
                DynamicEvent.trigger_date_start <= game_date,
                DynamicEvent.trigger_date_end >= game_date,
            )
        )
        return result.scalars().all()

    # ---- Event Activation ----

    async def fire_event(
        self, event: Event, phase: str = "active"
    ) -> EventContext | None:
        """Activate an event and return its context for prompt injection."""
        if phase == "active":
            event.phase = EventPhase.ACTIVE
            event.is_active = True
        elif phase == "transition":
            event.phase = EventPhase.TRANSITION

        await self.session.flush()

        rules = None
        if event.rules_appendix:
            rules = self.rulebook.load_rulebook(event.rules_appendix)

        return EventContext(
            event_id=event.id,
            event_name=event.name,
            event_type=event.event_type.value,
            phase=event.phase.value,
            ai_prompt=event.ai_setup_prompt or event.active_prompt,
            options=event.options,
            rules_appendix=rules,
            silent_effects=event.silent_effects,
        )

    async def advance_lifecycle(self, game_date: str) -> list[LifecycleAdvancement]:
        """Advance all events through their lifecycle for a new date."""
        result = await self.session.execute(select(Event))
        events = result.scalars().all()

        advancements = []
        for event in events:
            adv = await self.lifecycle.advance(event, game_date)
            if adv:
                advancements.append(adv)
                # Execute silent effects if any
                if adv.silent_effects and event.event_type == EventType.SILENT_FIXED:
                    await self._apply_silent_effects(event, adv.silent_effects)

        await self.session.flush()
        return advancements

    # ---- Choice Handling ----

    async def handle_choice(
        self, event_id: str, choice_id: str
    ) -> ChoiceResolution | None:
        """Resolve a player's event choice."""
        result = await self.session.execute(
            select(Event).where(Event.template_id == event_id)
        )
        event = result.scalar_one_or_none()
        if event is None or event.options is None:
            return None

        options = event.options if isinstance(event.options, list) else []
        chosen = None
        for opt in options:
            if opt.get("id") == choice_id:
                chosen = opt
                break

        if chosen is None:
            return None

        stat_changes = chosen.get("stat_changes", {})
        target_event_id = chosen.get("target_event")

        # Mark this event as complete if it has a target
        if target_event_id:
            self._completed_events.add(event.template_id)

        return ChoiceResolution(
            narrative_hook=chosen.get("text", ""),
            stat_changes=stat_changes,
            target_event_id=target_event_id,
        )

    # ---- Active Events Query ----

    async def get_active_events(self) -> list[Event]:
        result = await self.session.execute(
            select(Event).where(Event.is_active == True)
        )
        return result.scalars().all()

    async def get_active_contexts(self) -> list[EventContext]:
        events = await self.get_active_events()
        contexts = []
        for ev in events:
            rules = None
            if ev.rules_appendix:
                rules = self.rulebook.load_rulebook(ev.rules_appendix)
            contexts.append(EventContext(
                event_id=ev.id,
                event_name=ev.name,
                event_type=ev.event_type.value,
                phase=ev.phase.value,
                ai_prompt=ev.active_prompt or ev.ai_setup_prompt,
                options=ev.options,
                rules_appendix=rules,
                silent_effects=ev.silent_effects,
            ))
        return contexts

    # ---- Silent Effects Application ----

    async def _apply_silent_effects(self, event: Event, effects: dict) -> None:
        """Apply silent event effects (status tags, relation changes, etc.)."""
        from src.models import Character, SocialRelation, RelationType

        # Status tag changes
        tag_changes = effects.get("status_tag_changes", {})
        for role_id, tags in tag_changes.items():
            result = await self.session.execute(
                select(Character).where(Character.role_id == role_id)
            )
            char = result.scalar_one_or_none()
            if char:
                char.status_tags = tags

        # Relation changes
        rel_changes = effects.get("relation_changes", [])
        for rc in rel_changes:
            from_result = await self.session.execute(
                select(Character).where(Character.role_id == rc["from"])
            )
            to_result = await self.session.execute(
                select(Character).where(Character.role_id == rc["to"])
            )
            from_char = from_result.scalar_one_or_none()
            to_char = to_result.scalar_one_or_none()
            if from_char and to_char:
                rel = SocialRelation(
                    src_char_id=from_char.id,
                    dst_char_id=to_char.id,
                    relation_type=RelationType(rc["type"]),
                    reason=rc.get("reason", f"Event: {event.name}"),
                )
                self.session.add(rel)
