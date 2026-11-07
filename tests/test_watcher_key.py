"""Which key the watcher sends. Its own key wins, and the two headers mean different authority."""
from __future__ import annotations

from aindy_sdk.watcher import config as watcher_config
from aindy_sdk.watcher import signal_emitter
from aindy_sdk.watcher.session_tracker import SessionEvent
from aindy_sdk.watcher.signal_emitter import SignalEmitter


class _Response:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _sent_headers(monkeypatch, **keys) -> dict:
    seen: dict = {}

    def _urlopen(request, timeout=None):
        seen.update({name.lower(): value for name, value in request.header_items()})
        return _Response()

    monkeypatch.setattr(signal_emitter, "urlopen", _urlopen)
    emitter = SignalEmitter(api_url="http://runtime.test/watcher/signals", **keys)
    emitter._send_with_retry(
        [
            SessionEvent(
                signal_type="heartbeat",
                session_id="s",
                timestamp="2026-11-07T12:00:00Z",
                app_name="editor",
                window_title="",
                activity_type="work",
            )
        ]
    )
    return seen


def test_control_the_shared_key_is_sent_as_x_api_key(monkeypatch):
    headers = _sent_headers(monkeypatch, api_key="shared")

    assert headers["x-api-key"] == "shared"
    assert "x-platform-key" not in headers


def test_your_own_key_is_sent_as_x_platform_key(monkeypatch):
    headers = _sent_headers(monkeypatch, api_key="", watcher_key="aindy_mine")

    assert headers["x-platform-key"] == "aindy_mine"
    assert "x-api-key" not in headers


def test_your_own_key_wins_and_the_shared_one_is_not_sent(monkeypatch):
    headers = _sent_headers(monkeypatch, api_key="shared", watcher_key="aindy_mine")

    assert headers["x-platform-key"] == "aindy_mine"
    assert "x-api-key" not in headers


def _config(monkeypatch, **env):
    for name in ("AINDY_WATCHER_KEY", "AINDY_API_KEY", "AINDY_WATCHER_DRY_RUN"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return watcher_config.load()


def test_either_key_satisfies_validation(monkeypatch):
    assert watcher_config.validate(_config(monkeypatch, AINDY_WATCHER_KEY="aindy_mine")) == []
    assert watcher_config.validate(_config(monkeypatch, AINDY_API_KEY="shared")) == []


def test_no_key_fails_validation(monkeypatch):
    errors = watcher_config.validate(_config(monkeypatch))

    assert any("AINDY_WATCHER_KEY" in error for error in errors)


def test_the_loaded_key_reaches_the_config(monkeypatch):
    assert _config(monkeypatch, AINDY_WATCHER_KEY="aindy_mine").watcher_key == "aindy_mine"
