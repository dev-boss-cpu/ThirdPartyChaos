"""
ThirdPartyChaos -- Module 2: Failure Injector
Registers a chaos hook with Module 1 and implements all 10 fault patterns.
Shared fault state is stored via Redis (preferred) or a JSON file fallback
so the proxy process and the control API process stay in sync.
"""
import json
import random
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from mitmproxy import http

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).parent
ROOT = HERE.parent
LOG_PATH = ROOT / "module1" / "logs" / "chaos_run.jsonl"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
STATE_PATH    = ROOT / "module1" / "logs" / "fault_state.json"
INCIDENTS_PATH = ROOT / "incidents.json"

# Load incident traces once at import — enriches every injection log record
def _load_incidents() -> dict:
    if INCIDENTS_PATH.exists():
        try:
            return json.loads(INCIDENTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

_INCIDENTS: dict = _load_incidents()

# ---------------------------------------------------------------------------
# Shared state backend (Redis with file fallback)
# ---------------------------------------------------------------------------

class _FileStore:
    """File-based key/value store for cross-process fault state on Windows."""

    _lock = threading.Lock()

    def _read(self) -> dict:
        if STATE_PATH.exists():
            try:
                return json.loads(STATE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _write(self, data: dict) -> None:
        STATE_PATH.write_text(json.dumps(data), encoding="utf-8")

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            return self._read().get(key)

    def set(self, key: str, value) -> None:
        with self._lock:
            d = self._read()
            d[key] = value
            self._write(d)

    def delete(self, key: str) -> None:
        with self._lock:
            d = self._read()
            d.pop(key, None)
            self._write(d)

    def incr(self, key: str) -> int:
        with self._lock:
            d = self._read()
            val = int(d.get(key, 0)) + 1
            d[key] = val
            self._write(d)
            return val

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def rpush(self, key: str, value: str) -> None:
        with self._lock:
            d = self._read()
            lst = d.get(key, [])
            if not isinstance(lst, list):
                lst = []
            lst.append(value)
            d[key] = lst[-200:]        # cap log at 200 entries
            self._write(d)

    def lrange(self, key: str, start: int, end: int) -> list:
        with self._lock:
            lst = self._read().get(key, [])
            if not isinstance(lst, list):
                return []
            return lst[start:] if end == -1 else lst[start: end + 1]


def _make_store():
    try:
        import redis as _redis
        r = _redis.from_url("redis://localhost:6379", decode_responses=True,
                            socket_connect_timeout=1)
        r.ping()
        print("[TPC M2] Using Redis for shared fault state.")
        return r
    except Exception:
        print("[TPC M2] Redis not available — using file-based state store.")
        return _FileStore()


_store = _make_store()
_FAULT_KEY = "tpc:active_fault"

# ---------------------------------------------------------------------------
# In-process stats (proxy process only)
# ---------------------------------------------------------------------------
_stats_lock = threading.Lock()
_fault_stats: dict = {
    "injections": 0,
    "requests_seen": 0,
    "faults_by_type": {},
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_injection(fault: str, url: str) -> None:
    incident_info = _INCIDENTS.get(fault, {})
    record = {
        "event":            "injection",
        "fault":            fault,
        "url":              url,
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "incident_refs":    incident_info.get("real_incidents", []),
        "pattern_rationale": incident_info.get("pattern_rationale", ""),
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    with _stats_lock:
        _fault_stats["injections"] += 1
        _fault_stats["faults_by_type"][fault] = (
            _fault_stats["faults_by_type"].get(fault, 0) + 1
        )


def _make_response(status: int, body: str,
                   content_type: str = "application/json") -> http.Response:
    return http.Response.make(
        status,
        body.encode("utf-8"),
        {"Content-Type": content_type},
    )


# ---------------------------------------------------------------------------
# Fault implementations (10 fault patterns)
# ---------------------------------------------------------------------------

def _fault_timeout(flow: http.HTTPFlow) -> Optional[http.Response]:
    """Hang for a very long time — simulates an unresponsive upstream."""
    _log_injection("timeout", flow.request.pretty_url)
    flow.metadata["tpc_injected"] = True
    time.sleep(9999)
    return None


def _fault_slow_response(flow: http.HTTPFlow) -> Optional[http.Response]:
    """Inject 5-15 s of artificial latency before passing the response."""
    delay = random.uniform(5.0, 15.0)
    _log_injection("slow_response", flow.request.pretty_url)
    flow.metadata["tpc_injected"] = True
    time.sleep(delay)
    return None  # let the real response through after delay


def _fault_wrong_status_code(flow: http.HTTPFlow) -> Optional[http.Response]:
    """Return HTTP 402 Payment Required."""
    _log_injection("wrong_status_code", flow.request.pretty_url)
    flow.metadata["tpc_injected"] = True
    body = json.dumps({
        "error": {
            "code": "payment_required",
            "message": "Injected: 402 wrong status code by ThirdPartyChaos",
            "type": "invalid_request_error",
        }
    })
    return _make_response(402, body)


def _fault_corrupted_json(flow: http.HTTPFlow) -> Optional[http.Response]:
    """Corrupt JSON body on 5 % of requests."""
    if random.random() > 0.05:
        return None
    _log_injection("corrupted_json", flow.request.pretty_url)
    flow.metadata["tpc_injected"] = True
    garbage = '{"status":"ok","data":{invalid json here ' + \
        "".join(random.choices("abcdef}{][", k=20))
    return _make_response(200, garbage)


def _fault_silent_webhook_drop(flow: http.HTTPFlow) -> Optional[http.Response]:
    """Swallow webhook — return 200 but log nothing upstream."""
    if "webhook" not in flow.request.pretty_url.lower():
        return None
    _log_injection("silent_webhook_drop", flow.request.pretty_url)
    flow.metadata["tpc_injected"] = True
    return _make_response(200, json.dumps({"received": True}))


def _fault_partial_success(flow: http.HTTPFlow) -> Optional[http.Response]:
    """Payment 'accepted' but no confirmation id in the response."""
    _log_injection("partial_success", flow.request.pretty_url)
    flow.metadata["tpc_injected"] = True
    body = json.dumps({
        "object": "charge",
        "amount": 1000,
        "currency": "usd",
        "status": "pending",
        # deliberately omit "id"
    })
    return _make_response(200, body)


def _fault_rate_limit(flow: http.HTTPFlow) -> Optional[http.Response]:
    """Return 429 on 20 % of requests."""
    if random.random() > 0.20:
        return None
    _log_injection("rate_limit", flow.request.pretty_url)
    flow.metadata["tpc_injected"] = True
    body = json.dumps({
        "code": 20429,
        "message": "Too Many Requests -- injected by ThirdPartyChaos",
    })
    resp = _make_response(429, body)
    resp.headers["Retry-After"] = "60"
    return resp


def _fault_auth_failure(flow: http.HTTPFlow) -> Optional[http.Response]:
    """Expire the auth token mid-session."""
    _log_injection("auth_failure", flow.request.pretty_url)
    flow.metadata["tpc_injected"] = True
    body = json.dumps({
        "error": "token_expired",
        "error_description": "JWT expired -- injected by ThirdPartyChaos",
    })
    return _make_response(401, body)


def _fault_empty_response(flow: http.HTTPFlow) -> Optional[http.Response]:
    """Return HTTP 200 with a completely empty body."""
    _log_injection("empty_response", flow.request.pretty_url)
    flow.metadata["tpc_injected"] = True
    return _make_response(200, "")


def _fault_missing_fields(flow: http.HTTPFlow) -> Optional[http.Response]:
    """Strip critical fields from a JSON response."""
    _log_injection("missing_fields", flow.request.pretty_url)
    flow.metadata["tpc_injected"] = True
    body = json.dumps({"object": "charge", "livemode": False})
    return _make_response(200, body)


# ---------------------------------------------------------------------------
# Fault dispatch table
# ---------------------------------------------------------------------------
_FAULTS = {
    "timeout":             _fault_timeout,
    "slow_response":       _fault_slow_response,
    "wrong_status_code":   _fault_wrong_status_code,
    "corrupted_json":      _fault_corrupted_json,
    "silent_webhook_drop": _fault_silent_webhook_drop,
    "partial_success":     _fault_partial_success,
    "rate_limit":          _fault_rate_limit,
    "auth_failure":        _fault_auth_failure,
    "empty_response":      _fault_empty_response,
    "missing_fields":      _fault_missing_fields,
}
VALID_FAULTS = list(_FAULTS.keys())


# ---------------------------------------------------------------------------
# Hook function registered with Module 1
# ---------------------------------------------------------------------------

def chaos_hook(flow: http.HTTPFlow) -> Optional[http.Response]:
    """Called by Module 1 for every intercepted request."""
    with _stats_lock:
        _fault_stats["requests_seen"] += 1
    fault = _store.get(_FAULT_KEY)
    if fault is None or fault not in _FAULTS:
        return None
    return _FAULTS[fault](flow)


# ---------------------------------------------------------------------------
# Public API used by control_api.py
# ---------------------------------------------------------------------------

def set_fault(fault_name: str) -> bool:
    if fault_name not in _FAULTS:
        return False
    _store.set(_FAULT_KEY, fault_name)
    return True


def clear_fault() -> None:
    _store.delete(_FAULT_KEY)


def get_status() -> dict:
    with _stats_lock:
        return {
            "active_fault": _store.get(_FAULT_KEY),
            "stats": dict(_fault_stats),
            "valid_faults": VALID_FAULTS,
        }


# ---------------------------------------------------------------------------
# Register with Module 1 immediately on import
# ---------------------------------------------------------------------------
import sys as _sys
_sys.path.insert(0, str(ROOT / "module1"))
try:
    from interceptor import register_chaos_hook
    register_chaos_hook(chaos_hook)
except ImportError:
    print("[TPC M2] Could not import interceptor — hook not registered.")
