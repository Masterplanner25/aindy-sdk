"""
aindy.sandbox — Runtime sandbox posture and verification.

Provides a focused view of the runtime's sandbox configuration, requirement
satisfaction, and trusted-Python inventory via the ``GET /health/sandbox``
endpoint.  Use this instead of parsing the full ``/health`` or
``/health/detail`` payloads when you only need security-posture information.

Example::

    posture = client.sandbox.posture()

    # Check whether the deployment profile's requirements are met
    if not client.sandbox.requirements_satisfied():
        runner = posture["plugin_sandbox_posture"]["current"]["runner_type"]
        raise RuntimeError(f"Sandbox requirements not satisfied (runner={runner!r})")

    # Check whether any unboxed (trusted-Python) code is loaded
    if client.sandbox.trusted_python_present():
        count = posture["trusted_python_execution"]["total_count"]
        print(f"Warning: {count} trusted-Python module(s) are running in-process")
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from aindy_sdk.client import AINDYClient

__all__ = ["SandboxAPI"]

_SANDBOX_STATUS = "/health/sandbox"


class SandboxAPI:
    """Runtime sandbox posture and verification.

    Args:
        client: The ``AINDYClient`` instance that owns this sub-API.
    """

    def __init__(self, client: "AINDYClient") -> None:
        self._client = client

    def posture(self) -> dict[str, Any]:
        """Return the full sandbox posture payload from ``GET /health/sandbox``.

        Returns a dict with the following top-level keys:

        - ``plugin_sandbox_posture`` — active runner, assurance class, trust
          status, certification tier, and requirement satisfaction flags.
        - ``plugin_sandbox_platform`` — per-platform capability matrix.
        - ``sandbox_verification_posture`` — verification method, kernel
          observability, and assurance ceiling.
        - ``trusted_python_execution`` — inventory of trusted in-process Python
          extensions (sandboxing: none).
        - ``plugin_hosts`` — active plugin host inventory.
        - ``plugin_sandbox_attestation`` — launch-observed attestation summary.
        - ``runtime_conditions`` — list of active runtime condition records.

        Returns:
            Parsed sandbox posture dict.

        Example::

            p = client.sandbox.posture()
            runner = p["plugin_sandbox_posture"]["current"]["runner_type"]
            tier   = p["plugin_sandbox_posture"]["current"]["certification_tier"]
        """
        return self._client.get(_SANDBOX_STATUS)

    def requirements_satisfied(self) -> bool:
        """Return ``True`` if all deployment-profile sandbox requirements are met.

        Checks both ``assurance_class_satisfied`` and
        ``certification_tier_satisfied`` from the posture payload.  Either
        flag being ``False`` means the active runner does not meet the profile's
        declared requirements.

        Returns:
            ``True`` if both requirement flags are satisfied, ``False`` otherwise.
        """
        data = self.posture()
        req = data.get("plugin_sandbox_posture", {}).get("requirement_status", {})
        return bool(
            req.get("assurance_class_satisfied", False)
            and req.get("certification_tier_satisfied", False)
        )

    def trusted_python_present(self) -> bool:
        """Return ``True`` if any trusted in-process Python extensions are loaded.

        Trusted Python extensions run with full interpreter privileges and no
        sandbox boundary.  Their presence is an audit concern: any loaded module
        has unrestricted access to the process.

        Returns:
            ``True`` if at least one trusted-Python module or node is loaded.
        """
        data = self.posture()
        return bool(data.get("trusted_python_execution", {}).get("present", False))
