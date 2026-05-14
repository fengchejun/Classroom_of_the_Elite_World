from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.forecaster.event_pool import DynamicEventPool
from src.core.llm_gateway.gateway import LLMGateway
from src.core.prompt_pipeline.assembler import PromptAssembler
from src.core.time_engine.clock import TIME_SLOTS
from src.utils.logger import get_logger

logger = get_logger(__name__)


class Forecaster:
    """
    AI Forecaster (预言家系统).
    Periodically calls the LLM to generate small side events for the next 1-3 days.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.pool = DynamicEventPool(session)
        self.llm_gateway = LLMGateway()
        self.prompt_assembler = PromptAssembler()

    async def run(
        self,
        game_date: str,
        time_slot: str,
        active_events: list[dict] | None = None,
        npc_states: list[dict] | None = None,
    ) -> int:
        """
        Execute the forecaster cycle:
        1. Build the forecast prompt
        2. Send to LLM
        3. Parse generated events
        4. Add to dynamic events pool
        Returns number of events generated.
        """
        # Build forecast prompt
        messages = await self.prompt_assembler.assemble_forecast(
            game_date=game_date,
            time_slot=time_slot,
            active_events=active_events,
            npc_states=npc_states,
        )

        # Generate events via LLM
        try:
            generated = await self.llm_gateway.generate_forecast(messages)
        except Exception as e:
            logger.error(f"Forecaster LLM call failed: {e}")
            return 0

        if not generated:
            logger.info("Forecaster generated no events")
            return 0

        # Adjust dates to be relative to current game date
        current_date = datetime.strptime(game_date, "%Y-%m-%d")
        for event in generated:
            if "trigger_date_start" not in event or not event["trigger_date_start"]:
                event["trigger_date_start"] = game_date
            if "trigger_date_end" not in event or not event["trigger_date_end"]:
                end_date = current_date + timedelta(days=3)
                event["trigger_date_end"] = end_date.strftime("%Y-%m-%d")

        # Add to pool
        count = await self.pool.add_events(generated)
        logger.info(f"Forecaster generated {count} events for {game_date}")
        return count

    async def check_and_trigger(
        self,
        location_id: str,
        game_date: str,
    ) -> list[dict]:
        """Check for pending dynamic events at this location and date."""
        events = await self.pool.get_pending_for_location(location_id, game_date)
        result = []
        for event in events:
            result.append({
                "id": event.id,
                "name": event.name,
                "ai_setup_prompt": event.ai_setup_prompt,
                "options": event.options,
            })
            await self.pool.mark_triggered(event.id)
        return result

    async def maintenance(self, current_date: str) -> dict:
        """Run pool maintenance: expire old events, clean up."""
        expired = await self.pool.expire_old_events(current_date)
        stats = await self.pool.get_stats()
        return {
            "expired_this_run": expired,
            "pool_stats": {
                "total": stats.total,
                "pending": stats.pending,
                "triggered": stats.triggered,
                "expired": stats.expired,
            },
        }
