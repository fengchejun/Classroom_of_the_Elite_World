from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import Character as CharacterModel
from src.models import Secret, SecretKnowledge
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CharacterView:
    """The view of a character from a specific observer's perspective."""
    role_id: str
    name: str
    current_location_id: str | None
    status_tags: list[str]
    public_info: list[dict]
    visible_secrets: list[dict]   # Only secrets the observer knows
    class_name: str | None


class CharacterManager:
    """Manages character information with asymmetric information (泄密锁)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_character(
        self, role_id: str, observer_id: str = "player"
    ) -> CharacterView | None:
        """Get a character from the observer's perspective. Hidden secrets are filtered out."""
        result = await self.session.execute(
            select(CharacterModel)
            .where(CharacterModel.role_id == role_id)
            .options(selectinload(CharacterModel.secrets_known))
        )
        char = result.scalar_one_or_none()
        if char is None:
            return None

        visible_secrets = await self._get_visible_secrets(char, observer_id)

        return CharacterView(
            role_id=char.role_id,
            name=char.name,
            current_location_id=char.current_location_id,
            status_tags=char.status_tags or [],
            public_info=char.public_info or [],
            visible_secrets=visible_secrets,
            class_name=char.class_name,
        )

    async def get_all_characters_brief(
        self, observer_id: str = "player"
    ) -> list[dict]:
        """Get brief info for all characters (for location listing, etc.)."""
        result = await self.session.execute(select(CharacterModel))
        chars = result.scalars().all()
        return [
            {
                "role_id": c.role_id,
                "name": c.name,
                "current_location_id": c.current_location_id,
                "status_tags": c.status_tags or [],
                "class_name": c.class_name,
            }
            for c in chars
        ]

    async def update_location(self, role_id: str, location_id: str) -> None:
        """Update a character's current location."""
        result = await self.session.execute(
            select(CharacterModel).where(CharacterModel.role_id == role_id)
        )
        char = result.scalar_one_or_none()
        if char:
            char.current_location_id = location_id

    async def update_status_tags(self, role_id: str, tags: list[str]) -> None:
        result = await self.session.execute(
            select(CharacterModel).where(CharacterModel.role_id == role_id)
        )
        char = result.scalar_one_or_none()
        if char:
            char.status_tags = tags

    async def create_character(self, data: dict) -> CharacterModel:
        """Import a character from JSON data."""
        char = CharacterModel(
            role_id=data["role_id"],
            name=data["name"],
            current_location_id=data.get("current_location_id", "none"),
            status_tags=data.get("status_tags", ["normal"]),
            public_info=data.get("public_info", []),
            schedule_weights=data.get("schedule_weights"),
            class_name=data.get("class_name"),
        )
        self.session.add(char)
        await self.session.flush()
        return char

    async def _get_visible_secrets(
        self, char: CharacterModel, observer_id: str
    ) -> list[dict]:
        """Get secrets visible to the observer."""
        visible = []

        # Secrets owned by this character that the observer knows
        for sk in char.secrets_known:
            secret = sk.secret
            if secret and secret.is_public:
                visible.append({"info_id": secret.info_id, "content": secret.content})
                continue

            # Check if observer knows this secret
            for sk2 in secret.known_by if secret else []:
                if sk2.character_id == observer_id or (
                    hasattr(sk2.character, "role_id") and sk2.character.role_id == observer_id
                ):
                    visible.append({"info_id": secret.info_id, "content": secret.content})
                    break

        # Also check global secrets (not owned by this char but relevant)
        result = await self.session.execute(
            select(Secret).where(
                Secret.subject_char_id == char.id, Secret.is_public == True
            )
        )
        for secret in result.scalars().all():
            if not any(v["info_id"] == secret.info_id for v in visible):
                visible.append({"info_id": secret.info_id, "content": secret.content})

        return visible
