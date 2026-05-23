# aindy-sdk

Client SDK for the A.I.N.D.Y. runtime API.

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

client = AINDYClient(
    base_url="http://localhost:8000",
    api_key="aindy_your_platform_key",
)

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
