"""Discord config surface (Spec C3) — the env-driven knobs default safely + are secret.

The bot token + OAuth client secret are ``SecretStr`` (D-C3-3 credential posture);
the REST/gateway bases + the OAuth TTL carry sane defaults so the adapter is usable
from env alone (single bot per platform — D-C3-X-v1-reach).
"""

from __future__ import annotations

from persona_connectors.config import ConnectorConfig
from pydantic import SecretStr


def test_discord_defaults_are_unconfigured_but_sane() -> None:
    cfg = ConnectorConfig()
    assert cfg.discord_bot_token is None  # unset until configured (fail-fast at startup)
    assert cfg.discord_oauth_client_secret is None
    assert cfg.discord_api_base_url == "https://discord.com/api/v10"
    assert cfg.discord_gateway_url.startswith("wss://")
    assert cfg.discord_link_token_ttl_minutes == 15


def test_discord_credentials_are_secret() -> None:
    cfg = ConnectorConfig(
        discord_bot_token=SecretStr("tok"),  # type: ignore[arg-type]
        discord_oauth_client_secret=SecretStr("sec"),  # type: ignore[arg-type]
    )
    assert isinstance(cfg.discord_bot_token, SecretStr)
    assert "tok" not in str(cfg.discord_bot_token)  # SecretStr masks in repr/str
    assert cfg.discord_bot_token.get_secret_value() == "tok"
