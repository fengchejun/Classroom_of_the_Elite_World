from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.event_bus.bus import EventBus, EventContext, ChoiceResolution
from src.core.llm_gateway.gateway import LLMGateway, LLMResponse
from src.core.llm_gateway.tool_registry import ToolRegistry, tool_registry
from src.core.persona_graph.character import CharacterManager
from src.core.persona_graph.secret_manager import SecretManager
from src.core.persona_graph.social_graph import SocialGraph
from src.core.prompt_pipeline.assembler import AssemblyInput, PromptAssembler
from src.core.time_engine.clock import Clock, TimeState
from src.core.time_engine.scheduler import Scheduler
from src.core.time_engine.spotlight import Spotlight
from src.models import Character, DialogueLog, Event, GameSession, Location, StorySummary
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GameResponse:
    """The complete response returned to the frontend after processing player input."""
    narrative: str                  # LLM-generated narrative
    player_state: dict             # Current player state
    time_display: str              # Formatted time string
    location: dict                 # Current location info
    spotlight_npcs: list[dict]     # Visible NPCs
    available_choices: list[dict]  # Event choices (if any)
    triggered_events: list[str]    # Events triggered this turn


class GameService:
    """Main game loop orchestrator. Wires all core systems together."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.clock = Clock()
        self.scheduler = Scheduler()
        self.spotlight = Spotlight()
        self.event_bus = EventBus(session)
        self.llm_gateway = LLMGateway(tools=tool_registry)
        self.prompt_assembler = PromptAssembler()
        self.char_manager = CharacterManager(session)
        self.secret_manager = SecretManager(session)
        self.social_graph = SocialGraph(session)

    # ---- Main Game Loop ----

    async def handle_player_input(
        self,
        session_slug: str,
        user_input: str,
        choice_id: str | None = None,
        trigger_event: str | None = None,
    ) -> GameResponse:
        """
        Process a single player input through the complete game loop.

        1. Load session state
        2. Handle choice if applicable
        3. Check event triggers
        4. Run NPC spotlight
        5. Assemble prompt
        6. Send to LLM with tool calling
        7. Process LLM response (state changes, etc.)
        8. Record dialogue
        9. Return response
        """
        # Load session
        game_session = await self._get_or_create_session(session_slug)
        self.clock.set_time(game_session.game_date, game_session.time_slot)

        # Handle event choice if applicable
        choice_result = None
        if choice_id and trigger_event:
            choice_result = await self.event_bus.handle_choice(trigger_event, choice_id)

        # Sync player location
        player_loc = game_session.player_location_id
        if choice_result and choice_result.target_event_id:
            # Choice may have moved us
            pass

        # Check event triggers at current location
        trigger_matches = await self.event_bus.check_triggers(
            location_id=player_loc,
            game_date=self.clock.now.game_date,
            time_slot=self.clock.now.time_slot,
            player_char_id=game_session.player_char_id,
        )

        # Fire the highest priority match
        event_context = None
        if trigger_matches:
            top_match = trigger_matches[0]
            event_context = await self.event_bus.fire_event(top_match.event)

        # Get active event contexts
        active_contexts = await self.event_bus.get_active_contexts()

        # Get location description
        location = await self._get_location_description(player_loc)

        # Run spotlight on NPCs at this location
        npcs_at_location = await self._get_npcs_at_location(player_loc)
        spotlight_npcs = self.spotlight.select(
            present_npcs=npcs_at_location,
            player_char_id=game_session.player_char_id,
            force_include=self._get_event_npc_ids(event_context),
        )

        # Assemble prompt
        assembly_input = AssemblyInput(
            location_name=location.get("name", "未知地点"),
            location_description=location.get("description", ""),
            location_tags=location.get("tags", []),
            recent_dialogues=await self._get_recent_dialogues(session_slug),
            story_summaries=await self._get_story_summaries(session_slug),
            active_events=[
                {"name": ev.event_name, "active_prompt": ev.ai_prompt}
                for ev in (active_contexts or [])
            ],
            rules_appendix=event_context.rules_appendix if event_context else None,
            game_date=self.clock.now.game_date,
            time_slot=self.clock.now.time_slot,
            spotlight_npcs=[
                {"name": n.name, "brief_status": n.brief_status, "is_critical": n.is_critical}
                for n in spotlight_npcs
            ],
            player_stats={
                "class_points": game_session.class_points,
                "private_points": game_session.private_points,
            },
            user_input=user_input,
            choice_id=choice_id,
        )

        assembled = await self.prompt_assembler.assemble(assembly_input)

        # Send to LLM
        llm_response = await self.llm_gateway.chat(
            messages=assembled.messages,
            system=assembled.system_prompt,
        )

        # Process state changes from LLM response
        await self._apply_state_changes(game_session, llm_response)

        # Advance time if requested
        time_advance = llm_response.state_changes.get("time_advance_slots", 0)
        if time_advance > 0:
            await self._advance_time(game_session, time_advance)

        # Record dialogue
        await self._record_dialogue(
            session_id=game_session.id,
            user_input=user_input,
            llm_response=llm_response,
            choice_id=choice_id,
            event_id=event_context.event_id if event_context else None,
            location_id=player_loc,
        )

        # Build response
        choices = event_context.options if event_context else None
        if isinstance(choices, str):
            choices = json.loads(choices)
        if not isinstance(choices, list):
            choices = []

        return GameResponse(
            narrative=llm_response.narrative,
            player_state={
                "location_id": game_session.player_location_id,
                "class_points": game_session.class_points,
                "private_points": game_session.private_points,
            },
            time_display=f"{self.clock.now.game_date} {self.clock.now.time_slot}",
            location=location,
            spotlight_npcs=[
                {"name": n.name, "brief_status": n.brief_status, "is_critical": n.is_critical}
                for n in spotlight_npcs
            ],
            available_choices=[
                {"id": c.get("id"), "text": c.get("text")} for c in choices
            ],
            triggered_events=llm_response.triggered_events,
        )

    # ---- Settlement ----

    async def run_settlement(self, session_slug: str) -> list[dict]:
        """Run settlement when time slot / day changes."""
        game_session = await self._get_or_create_session(session_slug)
        self.clock.set_time(game_session.game_date, game_session.time_slot)

        results = []

        # Advance event lifecycles
        advancements = await self.event_bus.advance_lifecycle(self.clock.now.game_date)
        for adv in advancements:
            results.append({
                "type": "lifecycle_advance",
                "event_id": adv.event_id,
                "phase": adv.new_phase,
            })

        # Check if it's forecast time
        from src.config.settings import settings as app_settings
        if (
            self.clock.now.time_slot == app_settings.forecaster_schedule_slot
            and self.clock.day_of_week() == app_settings.forecaster_schedule_day - 1
        ):
            results.append({"type": "forecast_due", "message": "AI预言家应该在此刻运行"})

        # Check if dialogue summary is needed
        if game_session.dialogue_count_since_summary >= app_settings.dialogue_summary_threshold:
            results.append({"type": "summary_due", "count": game_session.dialogue_count_since_summary})

        return results

    # ---- Internal Helpers ----

    async def _advance_time(self, session: GameSession, slots: int) -> None:
        """Advance game time and run settlement."""
        self.clock.advance(slots)
        session.game_date = self.clock.now.game_date
        session.time_slot = self.clock.now.time_slot
        await self.session.flush()
        await self.run_settlement(session.session_slug)

    async def _apply_state_changes(self, session: GameSession, llm_response: LLMResponse) -> None:
        """Apply state changes from LLM response."""
        changes = llm_response.state_changes

        if "player_location" in changes and changes["player_location"]:
            session.player_location_id = changes["player_location"]

        if "class_points_delta" in changes:
            session.class_points += changes["class_points_delta"]

        if "private_points_delta" in changes:
            session.private_points += changes["private_points_delta"]

        await self.session.flush()

    async def _get_or_create_session(self, slug: str) -> GameSession:
        result = await self.session.execute(
            select(GameSession).where(GameSession.session_slug == slug)
        )
        sess = result.scalar_one_or_none()
        if sess is None:
            sess = GameSession(session_slug=slug)
            self.session.add(sess)
            await self.session.flush()
        return sess

    async def _get_location_description(self, location_id: str) -> dict:
        result = await self.session.execute(
            select(Location).where(Location.location_id == location_id)
        )
        loc = result.scalar_one_or_none()
        if loc:
            return {
                "name": loc.name,
                "description": loc.description,
                "tags": loc.tags or [],
                "connected_to": loc.connected_to or [],
                "zone_id": loc.zone_id,
            }
        return {"name": "未知地点", "description": "这是一个尚未被描述的地方。", "tags": [], "connected_to": []}

    async def _get_npcs_at_location(self, location_id: str) -> list[dict]:
        result = await self.session.execute(
            select(Character).where(Character.role_id != "player")
        )
        chars = result.scalars().all()

        visible = self.scheduler.get_visible_npcs(
            target_location=location_id,
            all_characters=[
                {
                    "char_id": c.role_id,
                    "name": c.name,
                    "schedule_weights": c.schedule_weights,
                    "status_tags": c.status_tags or [],
                    "class_name": c.class_name,
                    "default_location": c.current_location_id or "classroom_d",
                }
                for c in chars
            ],
            time_slot=self.clock.now.time_slot,
            day_of_week=self.clock.day_of_week(),
            is_weekend=self.clock.is_weekend(),
        )
        return visible

    async def _get_recent_dialogues(self, session_slug: str) -> list[dict]:
        session = await self._get_or_create_session(session_slug)
        result = await self.session.execute(
            select(DialogueLog)
            .where(DialogueLog.session_id == session.id)
            .order_by(DialogueLog.sequence_num.desc())
            .limit(10)
        )
        dialogues = result.scalars().all()
        return [
            {"user": d.user_input, "llm": d.llm_response}
            for d in reversed(dialogues)
        ]

    async def _get_story_summaries(self, session_slug: str) -> list[str]:
        session = await self._get_or_create_session(session_slug)
        result = await self.session.execute(
            select(StorySummary)
            .where(StorySummary.session_id == session.id)
            .order_by(StorySummary.dialogue_end_seq)
        )
        return [s.summary_text for s in result.scalars().all()]

    async def _record_dialogue(
        self,
        session_id: str,
        user_input: str,
        llm_response: LLMResponse,
        choice_id: str | None = None,
        event_id: str | None = None,
        location_id: str | None = None,
    ) -> None:
        # Get next sequence number
        result = await self.session.execute(
            select(func.max(DialogueLog.sequence_num)).where(
                DialogueLog.session_id == session_id
            )
        )
        max_seq = result.scalar() or 0

        log = DialogueLog(
            session_id=session_id,
            sequence_num=max_seq + 1,
            user_input=user_input,
            llm_response=llm_response.narrative,
            response_data={
                "state_changes": llm_response.state_changes,
                "triggered_events": llm_response.triggered_events,
                "npc_reactions": llm_response.npc_reactions,
            },
            choice_id=choice_id,
            event_id=event_id,
            location_at_time=location_id,
        )
        self.session.add(log)
        await self.session.flush()

        # Increment dialogue counter
        result = await self.session.execute(
            select(GameSession).where(GameSession.id == session_id)
        )
        sess = result.scalar_one_or_none()
        if sess:
            sess.dialogue_count_since_summary += 1

        await self.session.flush()

    @staticmethod
    def _get_event_npc_ids(event_context: EventContext | None) -> list[str]:
        """Extract forced NPC IDs from event context."""
        if event_context is None:
            return []
        # Could parse from event config; for now return empty
        return []
