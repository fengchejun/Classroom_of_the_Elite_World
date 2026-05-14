from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import Character, RelationType, SocialRelation
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SocialEdge:
    """A relationship link between two characters."""
    from_role_id: str
    from_name: str
    to_role_id: str
    to_name: str
    relation_type: str   # trust / hostile / subservient
    reason: str | None = None


@dataclass
class SocialNetworkView:
    """The complete social network around a character."""
    char_role_id: str
    char_name: str
    outgoing: list[SocialEdge]   # This char → others
    incoming: list[SocialEdge]   # Others → this char
    trust_allies: list[str]      # Names of trusted allies
    hostile_toward: list[str]    # Names of those they're hostile to
    fears: list[str]             # Names of those they're subservient to


class SocialGraph:
    """Manages the dynamic social network between characters."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_network(self, role_id: str) -> SocialNetworkView | None:
        """Get the full social network view for a character."""
        char = await self._get_char(role_id)
        if char is None:
            return None

        # Outgoing edges (this char → others)
        out_result = await self.session.execute(
            select(SocialRelation)
            .where(SocialRelation.src_char_id == char.id)
            .options(
                selectinload(SocialRelation.from_char),
                selectinload(SocialRelation.to_char),
            )
        )
        outgoing = [
            SocialEdge(
                from_role_id=char.role_id,
                from_name=char.name,
                to_role_id=r.to_char.role_id,
                to_name=r.to_char.name,
                relation_type=r.relation_type.value,
                reason=r.reason,
            )
            for r in out_result.scalars().all()
        ]

        # Incoming edges (others → this char)
        in_result = await self.session.execute(
            select(SocialRelation)
            .where(SocialRelation.dst_char_id == char.id)
            .options(
                selectinload(SocialRelation.from_char),
                selectinload(SocialRelation.to_char),
            )
        )
        incoming = [
            SocialEdge(
                from_role_id=r.from_char.role_id,
                from_name=r.from_char.name,
                to_role_id=char.role_id,
                to_name=char.name,
                relation_type=r.relation_type.value,
                reason=r.reason,
            )
            for r in in_result.scalars().all()
        ]

        trust_allies = [e.to_name for e in outgoing if e.relation_type == "trust"]
        hostile_toward = [e.to_name for e in outgoing if e.relation_type == "hostile"]
        fears = [e.to_name for e in outgoing if e.relation_type == "subservient"]

        return SocialNetworkView(
            char_role_id=char.role_id,
            char_name=char.name,
            outgoing=outgoing,
            incoming=incoming,
            trust_allies=trust_allies,
            hostile_toward=hostile_toward,
            fears=fears,
        )

    async def set_relation(
        self,
        from_role_id: str,
        to_role_id: str,
        relation_type: str,
        reason: str = "",
    ) -> SocialRelation | None:
        """Create or update a social relation between two characters."""
        from_char = await self._get_char(from_role_id)
        to_char = await self._get_char(to_role_id)
        if from_char is None or to_char is None:
            logger.warning(f"Relation failed: {from_role_id} or {to_role_id} not found")
            return None

        # Check if relation already exists
        result = await self.session.execute(
            select(SocialRelation).where(
                SocialRelation.src_char_id == from_char.id,
                SocialRelation.dst_char_id == to_char.id,
            )
        )
        existing = result.scalar_one_or_none()

        rt = RelationType(relation_type)

        if existing:
            existing.relation_type = rt
            existing.reason = reason
            await self.session.flush()
            return existing
        else:
            rel = SocialRelation(
                src_char_id=from_char.id,
                dst_char_id=to_char.id,
                relation_type=rt,
                reason=reason,
            )
            self.session.add(rel)
            await self.session.flush()
            return rel

    async def remove_relation(self, from_role_id: str, to_role_id: str) -> bool:
        """Remove a social relation entirely."""
        from_char = await self._get_char(from_role_id)
        to_char = await self._get_char(to_role_id)
        if from_char is None or to_char is None:
            return False

        result = await self.session.execute(
            select(SocialRelation).where(
                SocialRelation.src_char_id == from_char.id,
                SocialRelation.dst_char_id == to_char.id,
            )
        )
        rel = result.scalar_one_or_none()
        if rel:
            await self.session.delete(rel)
            await self.session.flush()
            return True
        return False

    async def get_faction_members(self, leader_role_id: str) -> list[dict]:
        """Get all characters that are subservient or trust the leader."""
        leader = await self._get_char(leader_role_id)
        if leader is None:
            return []

        result = await self.session.execute(
            select(SocialRelation)
            .where(
                SocialRelation.dst_char_id == leader.id,
                SocialRelation.relation_type.in_(
                    [RelationType.SUBSERVIENT, RelationType.TRUST]
                ),
            )
            .options(selectinload(SocialRelation.from_char))
        )
        members = []
        for r in result.scalars().all():
            members.append({
                "role_id": r.from_char.role_id,
                "name": r.from_char.name,
                "relation": r.relation_type.value,
                "reason": r.reason,
            })
        return members

    async def get_all_relations(self) -> list[SocialEdge]:
        """Get all social relations (for admin/debug)."""
        result = await self.session.execute(
            select(SocialRelation).options(
                selectinload(SocialRelation.from_char),
                selectinload(SocialRelation.to_char),
            )
        )
        return [
            SocialEdge(
                from_role_id=r.from_char.role_id,
                from_name=r.from_char.name,
                to_role_id=r.to_char.role_id,
                to_name=r.to_char.name,
                relation_type=r.relation_type.value,
                reason=r.reason,
            )
            for r in result.scalars().all()
        ]

    async def _get_char(self, role_id: str) -> Character | None:
        result = await self.session.execute(
            select(Character).where(Character.role_id == role_id)
        )
        return result.scalar_one_or_none()
