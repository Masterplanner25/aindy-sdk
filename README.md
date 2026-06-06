# aindy-sdk

Universal interface SDK for the A.I.N.D.Y. runtime API.

`aindy-sdk` is the local+cloud bridge: the same client code works against a
locally-installed runtime (where the operator owns the infrastructure) and a
cloud-hosted runtime (where the provider owns the infrastructure). Switching
deployment context requires only a `base_url` change — no application code
changes.

Part of the Masterplan Infinite Weave ecosystem by Shawn Knight.
Runtime infrastructure: https://github.com/Masterplanner25/aindy-runtime

## Install

```bash
pip install aindy-sdk
```

## Requirements

- Python 3.11+
- No external dependencies (stdlib only) for the API client
- Watcher subpackage optional dependencies: `psutil` (fallback window detection),
  `pyobjc-framework-AppKit` + `pyobjc-framework-Quartz` (macOS window titles),
  `xdotool` system package (Linux window detection)

---

## Getting started

### 1. Start the runtime

Install and start `aindy-runtime` ([full instructions](https://github.com/Masterplanner25/aindy-runtime#quickstart)):

```bash
git clone https://github.com/Masterplanner25/aindy-runtime.git
cd aindy-runtime
cp AINDY/.env.example AINDY/.env   # set SECRET_KEY and OPENAI_API_KEY at minimum
docker compose up -d
```

Wait until the server is ready:

```bash
curl http://localhost:8000/ready    # → {"status": "ok", ...}
```

### 2. Register and log in

```bash
# Register
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword", "display_name": "You"}' \
  | python -m json.tool

# Log in — copy the access_token from the response
curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}' \
  | python -m json.tool
```

To promote your account to admin (required to create API keys via the CLI):

```bash
# Using the CLI (no server restart needed)
aindy-runtime auth promote-admin you@example.com

# Or via env var (requires server restart)
# Add AINDY_BOOTSTRAP_ADMIN_EMAIL=you@example.com to AINDY/.env, then docker compose restart api
```

### 3. Create a Platform API key

Platform API keys start with `aindy_` and are shown only once — save the `key` field.

```bash
JWT="<your-access_token>"

curl -s -X POST http://localhost:8000/platform/keys \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-app",
    "scopes": ["memory.read", "memory.write", "flow.run", "event.emit"]
  }' \
  | python -m json.tool
```

**Available scopes:**

| Scope | Grants access to |
|---|---|
| `memory.read` | Read and search memory nodes |
| `memory.write` | Write and delete memory nodes |
| `flow.run` | Trigger flow runs |
| `event.emit` | Emit events to the event bus |
| `syscall.*` | Full syscall registry access |
| `execution.read` | Read execution unit status |

### 4. First call

```python
from aindy_sdk import AINDYClient

client = AINDYClient(
    base_url="http://localhost:8000",
    api_key="aindy_your_platform_key",
)

result = client.memory.read("/memory/you/notes/**", limit=5)
print(result["data"]["nodes"])
```

Run the full example:

```bash
AINDY_API_KEY=aindy_... python examples/quickstart.py
```

---

## Usage

```python
from aindy_sdk import AINDYClient

# Local runtime (operator owns infrastructure)
client = AINDYClient(
    base_url="http://localhost:8000",
    api_key="aindy_your_platform_key",
)

# Cloud-hosted — same code, different base_url
# client = AINDYClient(base_url="https://runtime.aindy.ai", api_key="...")

# Read memory
result = client.memory.read("/memory/shawn/entities/**", limit=5)
nodes = result["data"]["nodes"]

# Run a flow
analysis = client.flow.run("analyze_entities", {"data": nodes})

# Write memory
client.memory.write(
    "/memory/shawn/insights/outcome",
    analysis["data"].get("summary", ""),
    tags=["sdk-demo"],
)

# Emit an event
client.events.emit("analysis.completed", {"node_count": len(nodes)})
```

---

## API reference

All capabilities are accessed through namespaces on `AINDYClient`:

| Namespace | Description |
|---|---|
| `client.memory` | Read, write, and search memory nodes by MAS path or vector similarity |
| `client.flow` | Trigger flow runs and poll their status |
| `client.events` | Emit events to the runtime event bus |
| `client.nodus` | Compile and execute Nodus scripts |
| `client.syscalls` | List and inspect the syscall registry |
| `client.execution` | Introspect in-flight or completed execution units |
| `client.sandbox` | Query sandbox assurance posture |

Every method returns a **syscall envelope**:

```python
{
    "status":      "success",        # "success" or "error"
    "data":        { ... },          # payload — varies by call
    "trace_id":    "abc123...",      # for log correlation
    "duration_ms": 12,               # server-side execution time in ms
    "error":       None,             # error description when status == "error"
}
```

### Memory (`client.memory`)

```python
# Read nodes at a MAS path (glob patterns supported)
result = client.memory.read("/memory/shawn/entities/**", limit=10)
nodes = result["data"]["nodes"]

# Write a node
result = client.memory.write(
    "/memory/shawn/insights/daily-summary",
    "Worked on SDK documentation today.",
    tags=["insight", "daily"],
    node_type="insight",
)
node_id = result["data"]["node"]["id"]

# Semantic similarity search
result = client.memory.search("recent project decisions", limit=5)

# Delete a node
client.memory.delete(node_id)
```

### Flow (`client.flow`)

```python
# Trigger a flow run and get the result
result = client.flow.run("analyze_entities", {"data": nodes})
print(result["status"])    # "success" | "waiting" | "failed"

# For long-running flows: trigger and poll
result = client.flow.trigger("long_analysis", {"input": "..."})
run_id = result["data"]["run_id"]

import time
while True:
    status = client.execution.get(run_id)
    if status["data"]["status"] not in ("running", "waiting"):
        break
    time.sleep(2)
```

### Events (`client.events`)

```python
# Emit an event (can trigger waiting flows)
result = client.events.emit(
    "user.action.completed",
    {"user_id": "u-123", "action": "document_saved"},
)
```

### Nodus (`client.nodus`)

```python
# Execute a Nodus script
result = client.nodus.run_script(
    script="""
let greeting = "Hello from Nodus"
set_state("message", greeting)
emit("script.hello", {text: greeting})
""",
    input={},
)
print(result["nodus_status"])      # "complete" | "wait" | "error"
print(result["output_state"])      # dict of set_state() calls
print(result["events_emitted"])    # count of emit() calls
```

### Execution (`client.execution`)

```python
run = client.execution.get("run-abc123")
status = run["data"]["status"]          # "running" | "success" | "failed" | "waiting"
syscall_count = run["data"]["syscall_count"]
wall_time_ms = run["data"]["wall_time_ms"]  # accumulated wall-clock time (includes I/O wait)
```

### Syscalls (`client.syscalls`)

```python
registry = client.syscalls.list(version="v1")
print(registry["total_count"])
for action, spec in registry["syscalls"]["v1"].items():
    deprecated = " [DEPRECATED]" if spec.get("deprecated") else ""
    print(f"sys.v1.{action}{deprecated}")
```

---

## Error handling

The SDK maps HTTP status codes to typed exceptions so you can handle failure
cases explicitly rather than inspecting status codes:

```python
from aindy_sdk import AINDYClient
from aindy_sdk.exceptions import (
    AuthenticationError,    # 401 — key missing, invalid, or expired
    PermissionDeniedError,  # 403 — key scope doesn't include this capability
    NotFoundError,          # 404 — resource doesn't exist
    ValidationError,        # 422 — bad request shape or schema violation
    ResourceLimitError,     # 429 — syscall count or wall_time_ms exceeded
    ServerError,            # 5xx — unexpected runtime error
    NetworkError,           # connection refused, timeout, or DNS failure
    AINDYError,             # base class — catches all of the above
)

client = AINDYClient(base_url="http://localhost:8000", api_key="aindy_...")

try:
    result = client.memory.read("/memory/shawn/entities/**", limit=5)
except AuthenticationError:
    print("Invalid API key — check AINDY_API_KEY")
except PermissionDeniedError as exc:
    print(f"Key scope missing: {exc.message}")
    # exc.response contains the full server error payload
except ValidationError as exc:
    print(f"Bad request: {exc.message}")
except NetworkError as exc:
    print(f"Server unreachable: {exc.cause}")
except AINDYError as exc:
    print(f"Runtime error [{exc.status_code}]: {exc.message}")
```

All typed errors carry:
- `.message` — human-readable description
- `.status_code` — HTTP status code (`None` for `NetworkError`)
- `.response` — raw server JSON dict

---

## Watcher

The SDK ships the A.I.N.D.Y. Watcher client process. The watcher runs on your
machine, observes the active OS window, classifies your activity, and emits
structured signals to the runtime for flow triggering and session tracking.

```bash
# Start the watcher (requires AINDY_API_KEY and AINDY_WATCHER_API_URL)
python -m aindy_sdk.watcher.watcher

# Dry run — logs signals, no HTTP requests
python -m aindy_sdk.watcher.watcher --dry-run

# Custom poll interval and verbose logging
python -m aindy_sdk.watcher.watcher --poll-interval 10 --log-level DEBUG
```

Environment variables:

| Variable | Default | Description |
|---|---|---|
| `AINDY_WATCHER_API_URL` | `http://localhost:8000` | Runtime base URL |
| `AINDY_API_KEY` | _(required)_ | Service API key (`X-API-Key` header) |
| `AINDY_WATCHER_DRY_RUN` | `false` | Log signals only, no HTTP POST |
| `AINDY_WATCHER_POLL_INTERVAL` | `5` | Seconds between window samples |
| `AINDY_WATCHER_FLUSH_INTERVAL` | `10` | Seconds between signal batch flushes |
| `AINDY_WATCHER_BATCH_SIZE` | `20` | Signals per POST batch |
| `AINDY_WATCHER_CONFIRMATION_DELAY` | `30` | Seconds of focus before `session_started` fires |
| `AINDY_WATCHER_DISTRACTION_TIMEOUT` | `60` | Seconds of off-task time before distraction state |
| `AINDY_WATCHER_RECOVERY_DELAY` | `30` | Seconds of focus to recover from distraction |
| `AINDY_WATCHER_HEARTBEAT_INTERVAL` | `300` | Seconds between heartbeat signals |
| `AINDY_WATCHER_LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |

See `examples/watcher_demo.py` for a dry-run demonstration.

---

## Status

Beta. Part of the aindy-runtime 1.0.0 ecosystem.
