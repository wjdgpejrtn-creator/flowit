from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from toolset.adapters.internal.notification.email_send_tool import EmailSendTool
from toolset.adapters.internal.notification.slack_notify_tool import SlackNotifyTool
from toolset.domain.exceptions import ToolExecutionError


def make_slack_credential(url: str = "https://hooks.slack.com/services/T00/B00/xxx") -> MagicMock:
    cred = MagicMock()
    cred.value = url
    return cred


# ── SlackNotifyTool ───────────────────────────────────────────────────────────

class TestSlackNotifyTool:
    @pytest.mark.asyncio
    async def test_send_success(self):
        tool = SlackNotifyTool()
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await tool.execute(
                {"message": "Deploy complete"},
                credential=make_slack_credential(),
            )

        assert result["sent"] is True
        assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_send_with_optional_fields(self):
        tool = SlackNotifyTool()
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            await tool.execute(
                {"message": "Hello", "channel": "#general", "username": "Bot", "icon_emoji": ":robot:"},
                credential=make_slack_credential(),
            )

        _, call_kwargs = mock_client.post.call_args
        payload = call_kwargs.get("json", {})
        assert payload["channel"] == "#general"
        assert payload["username"] == "Bot"

    @pytest.mark.asyncio
    async def test_non_200_status_sent_false(self):
        tool = SlackNotifyTool()
        mock_resp = MagicMock()
        mock_resp.status_code = 403

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await tool.execute({"message": "test"}, credential=make_slack_credential())

        assert result["sent"] is False

    @pytest.mark.asyncio
    async def test_missing_credential_raises(self):
        tool = SlackNotifyTool()
        with pytest.raises(ToolExecutionError):
            await tool.execute({"message": "test"})

    @pytest.mark.asyncio
    async def test_request_error_raises(self):
        import httpx
        tool = SlackNotifyTool()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError("refused")
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            with pytest.raises(ToolExecutionError):
                await tool.execute({"message": "x"}, credential=make_slack_credential("https://bad.url"))


# ── EmailSendTool ─────────────────────────────────────────────────────────────

class TestEmailSendTool:
    @pytest.mark.asyncio
    async def test_send_success_with_credential(self):
        tool = EmailSendTool()
        mock_credential = MagicMock()
        mock_credential.value = "user@example.com:password123"

        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
            mock_smtp.__exit__ = MagicMock(return_value=False)
            mock_smtp_cls.return_value = mock_smtp

            result = await tool.execute(
                {
                    "smtp_host": "smtp.example.com",
                    "smtp_port": 587,
                    "from_address": "sender@example.com",
                    "to_addresses": ["alice@example.com", "bob@example.com"],
                    "subject": "Test",
                    "body": "Hello",
                },
                credential=mock_credential,
            )

        assert result["sent"] is True
        assert result["recipients_count"] == 2
        mock_smtp.sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_without_credential(self):
        tool = EmailSendTool()

        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
            mock_smtp.__exit__ = MagicMock(return_value=False)
            mock_smtp_cls.return_value = mock_smtp

            result = await tool.execute({
                "smtp_host": "smtp.example.com",
                "from_address": "sender@example.com",
                "to_addresses": ["alice@example.com"],
                "subject": "Hi",
                "body": "World",
            })

        assert result["sent"] is True
        mock_smtp.login.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_credential_format_raises(self):
        tool = EmailSendTool()
        bad_credential = MagicMock()
        bad_credential.value = "no-colon-here"

        with pytest.raises(ToolExecutionError) as exc_info:
            await tool.execute(
                {
                    "smtp_host": "smtp.example.com",
                    "from_address": "a@b.com",
                    "to_addresses": ["c@d.com"],
                    "subject": "x",
                    "body": "y",
                },
                credential=bad_credential,
            )
        assert "username:password" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_smtp_error_raises(self):
        import smtplib
        tool = EmailSendTool()

        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp_cls.side_effect = smtplib.SMTPConnectError(421, "Service unavailable")

            with pytest.raises(ToolExecutionError):
                await tool.execute({
                    "smtp_host": "bad.smtp.server",
                    "from_address": "a@b.com",
                    "to_addresses": ["c@d.com"],
                    "subject": "x",
                    "body": "y",
                })
