import logging

from core import structured_logging


def test_repeated_noise_filter_throttles_known_twitch_websocket_spam():
    noise_filter = structured_logging.RepeatedNoiseFilter(throttle_seconds=300)
    record = logging.LogRecord(
        name="twitchio.websocket",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Websocket connection was closed: None",
        args=(),
        exc_info=None,
    )

    assert noise_filter.filter(record) is True
    assert noise_filter.filter(record) is False


def test_repeated_noise_filter_keeps_different_twitch_errors():
    noise_filter = structured_logging.RepeatedNoiseFilter(throttle_seconds=300)
    record = logging.LogRecord(
        name="twitchio.websocket",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Websocket connection was closed: abnormal",
        args=(),
        exc_info=None,
    )

    assert noise_filter.filter(record) is True
    assert noise_filter.filter(record) is True
