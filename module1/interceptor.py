"""
ThirdPartyChaos -- Module 1: Proxy Interceptor
mitmproxy addon that logs all HTTP flows to JSONL and calls
registered chaos hooks for fault injection.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

from mitmproxy import http

# ---------------------------------------------------------------------------
# Log setup
# ---------------------------------------------------------------------------
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
INTERCEPT_LOG = LOG_DIR / "intercept.jsonl"

# ---------------------------------------------------------------------------
# Hook registry
# ---------------------------------------------------------------------------
_chaos_hooks: List[Callable] = []


def register_chaos_hook(fn: Callable) -> None:
    """Register a callable to be invoked on every intercepted HTTP flow."""
    _chaos_hooks.append(fn)
    print(f"[TPC M1] Chaos hook registered: {fn.__name__}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _log(record: dict) -> None:
    with INTERCEPT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# mitmproxy Addon
# ---------------------------------------------------------------------------

class InterceptorAddon:
    """
    mitmproxy addon: logs every HTTP flow and dispatches to chaos hooks.
    Set flow.response in request() to short-circuit upstream forwarding.
    """

    def request(self, flow: http.HTTPFlow) -> None:
        flow.metadata["tpc_start"] = time.monotonic()

        # Log the outgoing request
        _log({
            "event": "request",
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Dispatch registered chaos hooks
        for hook in _chaos_hooks:
            try:
                synthetic = hook(flow)
                if synthetic is not None:
                    flow.response = synthetic
                    return
            except Exception as exc:
                print(f"[TPC M1] Hook error ({hook.__name__}): {exc}")

    def response(self, flow: http.HTTPFlow) -> None:
        elapsed_ms = (
            time.monotonic() - flow.metadata.get("tpc_start", time.monotonic())
        ) * 1000

        _log({
            "event": "response",
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "status_code": flow.response.status_code,
            "latency_ms": round(elapsed_ms, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "injected": flow.metadata.get("tpc_injected", False),
        })


# mitmproxy expects an `addons` list when loading as an addon script
addons = [InterceptorAddon()]
