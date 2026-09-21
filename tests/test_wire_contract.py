"""Every payload the SDK sends, validated against the runtime's OWN schemas.

The rest of this suite mocks the dispatcher and asserts what the SDK sends — which is how
`events.emit` sent `type` for `event_type`, `upload_script` sent `source` for `content`, and
`flow.run` sent `input` for `initial_state`, all green, all 422 live. A pin on the SDK's own
output cannot catch a wire mismatch; only the other side's schema can. So this file imports the
runtime (a `[test]` dependency) and validates the captured payload with the runtime's validator
for syscalls and its pydantic request model for the HTTP route.

Two liveness controls at the bottom prove the validators reject a wrong shape: the 1.0.0 shapes
are asserted to FAIL. If a future runtime relaxes a schema so that both pass, those controls go
red and the test has to be re-thought — better than silently proving nothing.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

# The runtime's config reads the environment at import; give it a test-mode minimum.
os.environ.setdefault("TEST_MODE", "1")
os.environ.setdefault("AINDY_ALLOW_SQLITE", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "wire-contract")

runtime_registry = pytest.importorskip(
    "AINDY.kernel.syscall_registry", reason="aindy-runtime is a [test] dependency; install .[test]"
)
from AINDY.kernel.syscall_registry import SYSCALL_REGISTRY  # noqa: E402
from AINDY.kernel.syscall_versioning import validate_payload  # noqa: E402
from AINDY.routes.platform.schemas import NodusScriptUpload  # noqa: E402

from aindy_sdk import AINDYClient  # noqa: E402


def _client() -> AINDYClient:
    return AINDYClient(base_url="http://localhost:8000", api_key="aindy_test_key")


def _capture_syscall(method):
    """Run an SDK method with the dispatcher patched; return (syscall_name, payload)."""
    client = _client()
    with patch.object(client.syscalls, "call", return_value={"status": "success", "data": {}}) as m:
        method(client)
    (name, payload), _ = m.call_args
    return name, payload


def _assert_valid(name: str, payload: dict) -> None:
    entry = SYSCALL_REGISTRY.get(name)
    assert entry is not None, f"{name} is not a registered syscall"
    errors = validate_payload(entry.input_schema, payload)
    assert errors == [], f"{name}: the runtime rejects the SDK's payload {payload!r}: {errors}"


# ── syscalls ─────────────────────────────────────────────────────────────────────────────

def test_events_emit_matches_the_runtime_schema():
    name, payload = _capture_syscall(lambda c: c.events.emit("entity.updated", {"entity_id": "42"}))
    assert name == "sys.v1.event.emit"
    _assert_valid(name, payload)


def test_flow_run_matches_the_runtime_schema():
    name, payload = _capture_syscall(lambda c: c.flow.run("analyze_entities", {"nodes": []}))
    assert name == "sys.v1.flow.run"
    _assert_valid(name, payload)


def test_memory_write_matches_the_runtime_schema():
    name, payload = _capture_syscall(
        lambda c: c.memory.write("/memory/shawn/insights/x", "content", tags=["t"])
    )
    assert name == "sys.v1.memory.write"
    _assert_valid(name, payload)


@pytest.mark.parametrize("method, expected", [
    (lambda c: c.memory.read("/memory/shawn/insights"), "sys.v1.memory.read"),
    (lambda c: c.memory.search("q"), "sys.v1.memory.search"),
    (lambda c: c.memory.list("/memory/shawn"), "sys.v1.memory.list"),
    (lambda c: c.memory.tree("/memory/shawn/sprint"), "sys.v1.memory.tree"),
    (lambda c: c.memory.trace("/memory/shawn/decisions/outcome/abc", depth=3), "sys.v1.memory.trace"),
])
def test_memory_reads_match_the_runtime_schema(method, expected):
    name, payload = _capture_syscall(method)
    assert name == expected
    _assert_valid(name, payload)


def test_memory_tree_docstring_matches_the_runtime_output_schema():
    """The 1.0.0 docstring promised ``data["flat"]``; the runtime's output schema does not."""
    out = SYSCALL_REGISTRY.get("sys.v1.memory.tree").output_schema or {}
    assert "flat" not in (out.get("properties") or {})
    assert "tree" in out.get("required", []) and "node_count" in out.get("required", [])
    from aindy_sdk.memory import MemoryAPI

    assert 'result["data"]["flat"]' not in (MemoryAPI.tree.__doc__ or "")


# ── HTTP request models ───────────────────────────────────────────────────────────────

def test_upload_script_matches_the_runtime_request_model():
    client = _client()
    with patch.object(client, "post", return_value={"name": "s", "size_bytes": 1, "created_at": "x"}) as m:
        client.nodus.upload_script("my_script", 'set_state("x", 1)')
    (path, body), _ = m.call_args
    assert path == "/platform/nodus/upload"
    NodusScriptUpload(**body)  # raises ValidationError on a wrong key


# ── liveness controls: the 1.0.0 shapes must FAIL these validators ──────────────────

def test_control_the_1_0_0_event_shape_is_rejected():
    entry = SYSCALL_REGISTRY.get("sys.v1.event.emit")
    assert validate_payload(entry.input_schema, {"type": "x", "payload": {}}) != []


def test_control_the_1_0_0_upload_shape_is_rejected():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        NodusScriptUpload(name="s", source="x", overwrite=False)
