from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.event import DynamicEvent, EventType
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PoolStats:
    total: int
    pending: int
    triggered: int
    expired: int


class DynamicEventPool:
    """Manages the pool of AI-generated dynamic events."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_events(self, events_data: list[dict]) -> int:
        """Add newly generated events to the pool."""
        count = 0
        for data in events_data:
            event = DynamicEvent(
                name=data.get("name", "未命名事件"),
                event_type=EventType.AI_GUIDED_CHOICE,
                trigger_location=data.get("trigger_location"),
                trigger_date_start=data.get("trigger_date_start"),
                trigger_date_end=data.get("trigger_date_end"),
                ai_setup_prompt=data.get("ai_setup_prompt"),
                options=data.get("options"),
                expires_at=data.get("trigger_date_end"),
            )
            self.session.add(event)
            count += 1
        await self.session.flush()
        logger.info(f"Added {count} dynamic events to pool")
        return count

    async def get_pending_for_location(
        self, location_id: str, game_date: str
    ) -> list[DynamicEvent]:
        """Get pending events that match a location and date range."""
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

    async def mark_triggered(self, event_id: str) -> None:
        """Mark an event as triggered."""
        result = await self.session.execute(
            select(DynamicEvent).where(DynamicEvent.id == event_id)
        )
        event = result.scalar_one_or_none()
        if event:
            event.is_triggered = True
            await self.session.flush()

    async def expire_old_events(self, current_date: str) -> int:
        """Expire events whose trigger window has passed."""
        result = await self.session.execute(
            select(DynamicEvent).where(
                DynamicEvent.is_triggered == False,
                DynamicEvent.is_expired == False,
                DynamicEvent.trigger_date_end < current_date,
            )
        )
        expired = result.scalars().all()
        for event in expired:
            event.is_expired = True
        if expired:
            await self.session.flush()
            logger.info(f"Expired {len(expired)} dynamic events")
        return len(expired)

    async def get_stats(self) -> PoolStats:
        """Get pool statistics."""
        result = await self.session.execute(select(DynamicEvent))
        all_events = result.scalars().all()
        return PoolStats(
            total=len(all_events),
            pending=sum(1 for e in all_events if not e.is_triggered and not e.is_expired),
            triggered=sum(1 for e in all_events if e.is_triggered),
            expired=sum(1 for e in all_events if e.is_expired),
        )

    async def clear_expired(self) -> int:
        """Remove expired events from the database."""
        result = await self.session.execute(
            select(DynamicEvent).where(DynamicEvent.is_expired == True)
        )
        expired = result.scalars().all()
        for event in expired:
            await self.session.delete(event)
        if expired:
            await self.session.flush()
        return len(expired)
