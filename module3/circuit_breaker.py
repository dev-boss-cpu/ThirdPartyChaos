"""
ThirdPartyChaos -- Module 3: Circuit Breaker
State machine: CLOSED -> OPEN -> HALF_OPEN -> CLOSED
State is persisted via Redis (preferred) or file store so any process can read it.
"""
import json
import time
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

HERE = Path(__file__).parent
ROOT = HERE.parent
STATE_PATH = ROOT / "module1" / "logs" / "fault_state.json"
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Shared store (same file-backed store used by Module 2)
# ---------------------------------------------------------------------------

class _FileStore:
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
            val = self._read().get(key)
            return str(val) if val is not None else None

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
            d[key] = lst[-200:]
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
        print("[TPC M3] Using Redis for circuit breaker state.")
        return r
    except Exception:
        print("[TPC M3] Redis not available — using file-based CB state.")
        return _FileStore()


# ---------------------------------------------------------------------------
# Circuit states
# ---------------------------------------------------------------------------

class State(str, Enum):
    CLOSED    = "CLOSED"     # Normal: requests pass through
    OPEN      = "OPEN"       # Tripped: all requests blocked
    HALF_OPEN = "HALF_OPEN"  # Testing: one probe request allowed


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class CBConfig:
    failure_threshold: int   = 3     # consecutive failures before OPEN
    success_threshold: int   = 2     # successes in HALF_OPEN before CLOSE
    timeout_seconds:   float = 30.0  # OPEN -> HALF_OPEN wait
    window_seconds:    float = 60.0  # rolling window for failure counting
    redis_key_prefix:  str   = "tpc:cb:"


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """
    A shared-store–backed circuit breaker for a named service.

    Usage:
        cb = CircuitBreaker("stripe")
        if cb.allow_request():
            try:
                result = call_stripe()
                cb.record_success()
            except Exception:
                cb.record_failure()
                raise
        else:
            raise RuntimeError("Circuit OPEN -- using fallback")
    """

    def __init__(self, service: str, config: CBConfig = None,
                 store=None):
        self.service = service
        self.cfg = config or CBConfig()
        self._store = store or _make_store()
        pfx = self.cfg.redis_key_prefix + service
        self._state_key    = f"{pfx}:state"
        self._fail_key     = f"{pfx}:failures"
        self._ok_key       = f"{pfx}:successes"
        self._opened_key   = f"{pfx}:opened_at"
        self._log_key      = f"{pfx}:event_log"

        if not self._store.exists(self._state_key):
            self._set_state(State.CLOSED)

    # -- State helpers

    def _set_state(self, state: State) -> None:
        self._store.set(self._state_key, state.value)
        ts = datetime.now(timezone.utc).isoformat()
        self._store.rpush(
            self._log_key,
            json.dumps({"state": state.value, "ts": ts, "service": self.service})
        )
        print(f"[CB:{self.service}] -> {state.value} at {ts}")

    def _get_state(self) -> State:
        raw = self._store.get(self._state_key)
        try:
            return State(raw) if raw else State.CLOSED
        except ValueError:
            return State.CLOSED

    # -- Core interface

    def allow_request(self) -> bool:
        state = self._get_state()
        if state == State.CLOSED:
            return True
        if state == State.OPEN:
            opened_at = float(self._store.get(self._opened_key) or 0)
            if time.time() - opened_at >= self.cfg.timeout_seconds:
                self._set_state(State.HALF_OPEN)
                self._store.set(self._ok_key, 0)
                return True      # allow ONE probe
            return False
        if state == State.HALF_OPEN:
            return True          # allow probe
        return False

    def record_success(self) -> None:
        state = self._get_state()
        if state == State.HALF_OPEN:
            successes = self._store.incr(self._ok_key)
            if successes >= self.cfg.success_threshold:
                self._store.set(self._fail_key, 0)
                self._set_state(State.CLOSED)
        elif state == State.CLOSED:
            self._store.set(self._fail_key, 0)

    def record_failure(self) -> None:
        state = self._get_state()
        if state in (State.CLOSED, State.HALF_OPEN):
            failures = self._store.incr(self._fail_key)
            if failures >= self.cfg.failure_threshold:
                self._store.set(self._opened_key, str(time.time()))
                self._set_state(State.OPEN)

    def get_state_snapshot(self) -> dict:
        return {
            "service":    self.service,
            "state":      self._get_state().value,
            "failures":   int(self._store.get(self._fail_key) or 0),
            "successes":  int(self._store.get(self._ok_key) or 0),
            "event_log":  [
                json.loads(e)
                for e in self._store.lrange(self._log_key, -10, -1)
            ],
        }

    def save_snapshot(self, path: Path = None) -> None:
        snap = self.get_state_snapshot()
        out  = path or ROOT / "healer_state.json"
        existing: list = []
        if out.exists():
            try:
                existing = json.loads(out.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        existing.append(snap)
        out.write_text(json.dumps(existing, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    cb = CircuitBreaker("stripe-test")
    print("Initial state:", cb.get_state_snapshot()["state"])
    for i in range(4):
        cb.record_failure()
        print(f"After failure {i+1}:", cb.get_state_snapshot()["state"])
    print("Allow request?", cb.allow_request())
    cb.save_snapshot()
    print("Snapshot saved.")
