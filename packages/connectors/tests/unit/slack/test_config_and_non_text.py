"""Slack config surface + non-text declines (Spec C3)."""

from __future__ import annotations

from persona_connectors.config import ConnectorConfig
from persona_connectors.domain.system_replies import DECLINE_MEDIA, DECLINE_UNKNOWN
from persona_connectors.slack.inbound import SlackNonTextKind
from persona_connectors.slack.non_text import decline_message
from pydantic import SecretStr


def test_slack_defaults_are_unconfigured_but_sane() -> None:
    cfg = ConnectorConfig()
    assert cfg.slack_bot_token is None
    assert cfg.slack_app_token is None
    assert cfg.slack_signing_secret is None
    assert cfg.slack_api_base_url == "https://slack.com/api"
    assert cfg.slack_transport == "socket"  # zero-infra default (D-C3-2)
    assert cfg.slack_link_token_ttl_minutes == 15


def test_slack_credentials_are_secret() -> None:
    cfg = ConnectorConfig(
        slack_bot_token=SecretStr("xoxb-tok"),  # type: ignore[arg-type]
        slack_signing_secret=SecretStr("sign"),  # type: ignore[arg-type]
    )
    assert isinstance(cfg.slack_bot_token, SecretStr)
    assert "xoxb-tok" not in str(cfg.slack_bot_token)
    assert cfg.slack_bot_token.get_secret_value() == "xoxb-tok"


def test_decline_copy_maps_per_kind() -> None:
    assert decline_message(SlackNonTextKind.media) == DECLINE_MEDIA
    assert decline_message(SlackNonTextKind.unknown) == DECLINE_UNKNOWN


def test_every_kind_has_a_decline() -> None:
    for kind in SlackNonTextKind:
        assert decline_message(kind)
