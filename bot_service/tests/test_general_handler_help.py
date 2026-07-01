from types import SimpleNamespace

import pytest

from bots.mixins.general_handler_mixin import GeneralHandlerMixin, HELP_STUB_TEXT


class _Handler(GeneralHandlerMixin):
    def __init__(self):
        import logging

        self.logger = logging.getLogger("test.general_handler_help")


@pytest.mark.asyncio
async def test_help_returns_viewer_dashboard_stub_for_twitch():
    handler = _Handler()
    sent_messages: list[str] = []

    class _Ctx:
        author = SimpleNamespace(name="viewer")
        channel = SimpleNamespace(name="channel")

        async def send(self, message: str):
            sent_messages.append(message)

    await handler._handle_help(_Ctx(), bot=None, args="", platform="twitch", db=None)

    assert sent_messages == [f"@viewer {HELP_STUB_TEXT}"]


@pytest.mark.asyncio
async def test_help_returns_viewer_dashboard_stub_for_vk():
    handler = _Handler()
    sent_messages: list[tuple[str, str]] = []

    class _VkBot:
        async def send_message(self, channel_name: str, message: str):
            sent_messages.append((channel_name, message))

    await handler._handle_help_vk(
        channel_name="vk_channel",
        author_name="viewer",
        author_id="1",
        args="",
        vk_bot=_VkBot(),
        message_data={},
        db=None,
    )

    assert sent_messages == [("vk_channel", f"@viewer {HELP_STUB_TEXT}")]
