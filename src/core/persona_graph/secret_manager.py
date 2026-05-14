from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import Character, Secret, SecretKnowledge
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SecretManager:
    """Manages the asymmetric secret system with unlock/lock enforcement."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_secret(
        self,
        info_id: str,
        content: str,
        subject_char_id: str | None = None,
        initially_known_by: list[str] | None = None,
    ) -> Secret:
        """Create a new secret. initially_known_by is list of character role_ids."""
        secret = Secret(
            info_id=info_id,
            content=content,
            subject_char_id=subject_char_id,
            is_public=False,
        )
        self.session.add(secret)
        await self.session.flush()

        for role_id in (initially_known_by or []):
            char = await self._get_char_by_role_id(role_id)
            if char:
                sk = SecretKnowledge(
                    secret_id=secret.id,
                    character_id=char.id,
                    unlocked_reason="initial knowledge",
                )
                self.session.add(sk)

        await self.session.flush()
        return secret

    async def check_access(self, secret_info_id: str, observer_role_id: str) -> bool:
        """Check if an observer has access to a secret."""
        result = await self.session.execute(
            select(Secret)
            .where(Secret.info_id == secret_info_id)
            .options(selectinload(Secret.known_by))
        )
        secret = result.scalar_one_or_none()
        if secret is None:
            return False
        if secret.is_public:
            return True
        for sk in secret.known_by:
            # Get the character's role_id
            char_result = await self.session.execute(
                select(Character).where(Character.id == sk.character_id)
            )
            char = char_result.scalar_one_or_none()
            if char and char.role_id == observer_role_id:
                return True
        return False

    async def unlock(
        self, secret_info_id: str, target_role_id: str, reason: str = ""
    ) -> bool:
        """Grant a character knowledge of a secret. Returns True if newly unlocked."""
        result = await self.session.execute(
            select(Secret)
            .where(Secret.info_id == secret_info_id)
            .options(selectinload(Secret.known_by))
        )
        secret = result.scalar_one_or_none()
        if secret is None:
            logger.warning(f"Secret not found: {secret_info_id}")
            return False

        char = await self._get_char_by_role_id(target_role_id)
        if char is None:
            logger.warning(f"Character not found: {target_role_id}")
            return False

        # Check if already known
        for sk in secret.known_by:
            if sk.character_id == char.id:
                return False  # Already known

        sk = SecretKnowledge(
            secret_id=secret.id,
            character_id=char.id,
            unlocked_reason=reason,
        )
        self.session.add(sk)
        await self.session.flush()
        logger.info(f"Secret '{secret_info_id}' unlocked for '{target_role_id}'")
        return True

    async def broadcast(self, secret_info_id: str) -> bool:
        """Make a secret public knowledge for all characters."""
        result = await self.session.execute(
            select(Secret).where(Secret.info_id == secret_info_id)
        )
        secret = result.scalar_one_or_none()
        if secret is None:
            return False
        secret.is_public = True
        await self.session.flush()
        logger.info(f"Secret '{secret_info_id}' is now public")
        return True

    async def get_known_secrets(self, role_id: str) -> list[dict]:
        """List all secrets a character knows."""
        char = await self._get_char_by_role_id(role_id)
        if char is None:
            return []

        result = await self.session.execute(
            select(SecretKnowledge)
            .where(SecretKnowledge.character_id == char.id)
            .options(selectinload(SecretKnowledge.secret))
        )
        return [
            {
                "info_id": sk.secret.info_id,
                "content": sk.secret.content,
                "unlocked_reason": sk.unlocked_reason,
            }
            for sk in result.scalars().all()
            if sk.secret
        ]

    async def _get_char_by_role_id(self, role_id: str) -> Character | None:
        result = await self.session.execute(
            select(Character).where(Character.role_id == role_id)
        )
        return result.scalar_one_or_none()
