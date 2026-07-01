from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bots.twitch_bot import Bot
from bots.vk_live_bot_core import VKLiveBotCore
from utils.tts_message_context import extract_twitch_tts_context
from utils.vk_chat_parser import extract_vk_mentioned_users, extract_vk_reply_metadata


def test_extract_twitch_tts_context_detects_reply_and_mentions():
    message = SimpleNamespace(
        content="hello @viewer and @viewer2",
        tags={
            "reply-parent-msg-id": "abc123",
            "reply-parent-user-login": "streamer",
        },
    )

    context = extract_twitch_tts_context(message)

    assert context["is_reply"] is True
    assert context["mentioned_users"] == ["viewer", "viewer2"]


def test_extract_vk_reply_and_mentions_from_payload():
    parts = [
        {"mention": {"nick": "ReplyTarget"}},
        {"text": {"content": " привет"}},
    ]
    message = {
        "reply": {
            "author": {"nick": "OriginalAuthor"},
            "parts": [{"text": {"content": "исходное сообщение"}}],
        }
    }

    mentioned_users = extract_vk_mentioned_users(parts, None, "@fallback")
    reply_metadata = extract_vk_reply_metadata(message)

    assert mentioned_users == ["replytarget", "fallback"]
    assert reply_metadata["is_reply"] is True
    assert reply_metadata["reply_to_author"] == "OriginalAuthor"
    assert reply_metadata["reply_to_text"] == "исходное сообщение"


@pytest.mark.asyncio
async def test_twitch_handle_tts_passes_reply_and_mentions_to_handler():
    bot = Bot.__new__(Bot)
    bot.tts_api = object()
    bot.connection_manager = object()
    message = SimpleNamespace(
        content="hello @viewer",
        author=SimpleNamespace(name="AuthorName"),
        channel=SimpleNamespace(name="ChannelName"),
        tags={
            "id": "msg-1",
            "reply-parent-msg-id": "reply-1",
            "custom-reward-id": "reward-1",
        },
    )

    with patch("utils.websocket_helper.handle_tts_for_message", new_callable=AsyncMock) as mock_handler:
        await Bot._handle_tts(bot, message)

    kwargs = mock_handler.await_args.kwargs
    assert kwargs["is_reply"] is True
    assert kwargs["mentioned_users"] == ["viewer"]
    assert kwargs["reward_id"] == "reward-1"
    assert kwargs["message_id"] == "msg-1"


@pytest.mark.asyncio
async def test_vk_handle_tts_passes_reply_and_mentions_to_handler():
    bot = VKLiveBotCore.__new__(VKLiveBotCore)
    bot.tts_api = object()
    bot.connection_manager = object()
    message = {"id": "vk-msg-1"}

    with patch("utils.websocket_helper.handle_tts_for_message", new_callable=AsyncMock) as mock_handler:
        await VKLiveBotCore._handle_vk_tts(
            bot,
            message,
            "channel_slug",
            "ViewerName",
            "reply text",
            is_reply=True,
            mentioned_users=["streamer", "moderator"],
        )

    kwargs = mock_handler.await_args.kwargs
    assert kwargs["is_reply"] is True
    assert kwargs["mentioned_users"] == ["streamer", "moderator"]
    assert kwargs["message_id"] == "vk-msg-1"
