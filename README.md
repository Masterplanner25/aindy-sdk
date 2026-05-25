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
- No external dependencies (stdlib only)

## Usage

```python
from aindy_sdk import AINDYClient

# Local install — operator owns the runtime
client = AINDYClient(
    base_url="http://localhost:8000",
    api_key="aindy_your_platform_key",
)

# Cloud-hosted — same code, different base_url
# client = AINDYClient(base_url="https://runtime.aindy.ai", api_key="...")

result = client.memory.read("/memory/shawn/entities/**", limit=5)
analysis = client.flow.run("analyze_entities", {"data": result["data"]["nodes"]})
client.memory.write(
    "/memory/shawn/insights/outcome",
    analysis["data"].get("summary", ""),
    tags=["sdk-demo"],
)
```

## Status

Beta. Part of the aindy-runtime 1.0.0 ecosystem.
