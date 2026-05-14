from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.core.persona_graph.secret_manager import SecretManager
from src.core.persona_graph.social_graph import SocialEdge, SocialNetworkView


class TestSecretManager:
    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    async def test_check_access_public(self, mock_session):
        from src.models import Secret

        secret = Secret(info_id="s1", content="test", is_public=True)
        mock_session.execute.return_value.scalar_one_or_none.return_value = secret

        mgr = SecretManager(mock_session)
        result = await mgr.check_access("s1", "player")
        assert result is True


class TestSocialGraph:
    async def test_social_edge_creation(self):
        edge = SocialEdge(
            from_role_id="a", from_name="A",
            to_role_id="b", to_name="B",
            relation_type="trust", reason="allies",
        )
        assert edge.relation_type == "trust"
        assert edge.from_name == "A"

    async def test_network_view_attributes(self):
        view = SocialNetworkView(
            char_role_id="char_1",
            char_name="Character",
            outgoing=[],
            incoming=[],
            trust_allies=["Alice"],
            hostile_toward=["Bob"],
            fears=["Ryuen"],
        )
        assert "Alice" in view.trust_allies
        assert "Ryuen" in view.fears
        assert len(view.hostile_toward) == 1
