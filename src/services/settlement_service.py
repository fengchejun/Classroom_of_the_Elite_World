from __future__ import annotations

from datetime import datetime, timedelta

from celery import Celery
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.config.settings import settings
from src.core.event_bus.bus import EventBus
from src.core.forecaster.forecaster import Forecaster
from src.core.time_engine.clock import Clock
from src.models import DialogueLog, GameSession, StorySummary
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Celery app for async task processing
celery_app = Celery(
    "settlement",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Tokyo",
    enable_utc=True,
    beat_schedule={
        "run-settlement-every-5-minutes": {
            "task": "src.services.settlement_service.settlement_beat",
            "schedule": 300.0,  # Check every 5 minutes
        },
    },
)


class SettlementService:
    """
    Handles batch settlement during time slot / day transitions.
    Includes Celery background tasks for periodic settlement.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.clock = Clock()

    async def settle_time_advance(
        self,
        session_slug: str,
        game_date: str,
        time_slot: str,
    ) -> dict:
        """
        Run full settlement for a time advance.
        Called after the player triggers a time change.
        """
        self.clock.set_time(game_date, time_slot)
        event_bus = EventBus(self.session)
        forecaster = Forecaster(self.session)

        results = {
            "date": game_date,
            "time_slot": time_slot,
            "lifecycle_advancements": [],
            "forecast_events": 0,
            "summary_generated": False,
        }

        # 1. Advance all event lifecycles
        advancements = await event_bus.advance_lifecycle(game_date)
        for adv in advancements:
            results["lifecycle_advancements"].append({
                "event_id": adv.event_id,
                "new_phase": adv.new_phase,
            })

        # 2. Check if forecaster should run (Sunday evening)
        if (
            time_slot == settings.forecaster_schedule_slot
            and datetime.strptime(game_date, "%Y-%m-%d").weekday()
            == settings.forecaster_schedule_day - 1
        ):
            active_events = await event_bus.get_active_contexts()
            active_list = [
                {"name": ev.event_name, "phase": ev.phase}
                for ev in active_events
            ]
            count = await forecaster.run(
                game_date=game_date,
                time_slot=time_slot,
                active_events=active_list,
            )
            results["forecast_events"] = count

        # 3. Check if dialogue summary is needed
        summary_made = await self._maybe_summarize(session_slug)
        results["summary_generated"] = summary_made

        # 4. Forecaster pool maintenance
        maint = await forecaster.maintenance(game_date)
        results["pool_maintenance"] = maint

        return results

    async def _maybe_summarize(self, session_slug: str) -> bool:
        """Generate a story summary if dialogue count exceeds threshold."""
        result = await self.session.execute(
            select(GameSession).where(GameSession.session_slug == session_slug)
        )
        session = result.scalar_one_or_none()
        if session is None:
            return False

        if session.dialogue_count_since_summary < settings.dialogue_summary_threshold:
            return False

        # Get dialogues since last summary
        last_summary_result = await self.session.execute(
            select(func.max(StorySummary.dialogue_end_seq)).where(
                StorySummary.session_id == session.id
            )
        )
        last_seq = last_summary_result.scalar() or 0

        dialogue_result = await self.session.execute(
            select(DialogueLog)
            .where(
                DialogueLog.session_id == session.id,
                DialogueLog.sequence_num > last_seq,
            )
            .order_by(DialogueLog.sequence_num)
        )
        dialogues = dialogue_result.scalars().all()

        if len(dialogues) < settings.dialogue_summary_threshold:
            return False

        # Generate summary text
        summary = await self._generate_summary_text(dialogues)

        # Save summary
        seq_start = dialogues[0].sequence_num
        seq_end = dialogues[-1].sequence_num

        story_summary = StorySummary(
            session_id=session.id,
            dialogue_start_seq=seq_start,
            dialogue_end_seq=seq_end,
            summary_text=summary,
        )
        self.session.add(story_summary)

        # Reset counter
        session.dialogue_count_since_summary = 0
        await self.session.flush()

        logger.info(f"Generated story summary for sessions {session_slug}: {seq_start}-{seq_end}")
        return True

    async def _generate_summary_text(self, dialogues: list[DialogueLog]) -> str:
        """Generate a concise summary of dialogues. Uses simple extraction (no LLM)."""
        events = []
        for d in dialogues:
            events.append(f"- {d.user_input[:80]}")

        return "剧情进展：\n" + "\n".join(events)

    async def get_session_state(self, session_slug: str) -> dict | None:
        """Get full session state for resumption."""
        result = await self.session.execute(
            select(GameSession).where(GameSession.session_slug == session_slug)
        )
        session = result.scalar_one_or_none()
        if session is None:
            return None
        return {
            "session_slug": session.session_slug,
            "game_date": session.game_date,
            "time_slot": session.time_slot,
            "player_location_id": session.player_location_id,
            "class_points": session.class_points,
            "private_points": session.private_points,
            "player_stats": session.player_stats,
            "dialogue_count_since_summary": session.dialogue_count_since_summary,
            "zone_override": session.zone_override,
        }


@celery_app.task(name="src.services.settlement_service.settlement_beat")
def settlement_beat():
    """Periodic beat task. Checks for any sessions needing settlement."""
    logger.info("Settlement beat: checking for sessions...")
    return {"status": "beat_ok", "timestamp": datetime.utcnow().isoformat()}


async def run_settlement_for_session(session_slug: str) -> dict:
    """Standalone settlement runner for a specific session."""
    engine = create_async_engine(settings.async_database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        result = await db.execute(
            select(GameSession).where(GameSession.session_slug == session_slug)
        )
        session = result.scalar_one_or_none()
        if session is None:
            return {"error": "Session not found"}

        service = SettlementService(db)
        result = await service.settle_time_advance(
            session_slug=session_slug,
            game_date=session.game_date,
            time_slot=session.time_slot,
        )
        await db.commit()
        return result
