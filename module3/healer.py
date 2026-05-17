"""
ThirdPartyChaos -- Module 3: Runtime Self-Healer
Monitors circuit breakers and activates fallback strategies automatically.
Run: python module3/healer.py
"""
import json
import sys
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from circuit_breaker import CircuitBreaker, State

HEALER_STATE = ROOT / "healer_state.json"

# ---------------------------------------------------------------------------
# Fallback provider map
# ---------------------------------------------------------------------------
FALLBACKS = {
    "stripe":   ["stripe-backup-key", "paypal-gateway"],
    "twilio":   ["vonage", "messagebird"],
    "auth0":    ["cognito", "firebase-auth"],
    "sendgrid": ["mailgun", "ses"],
}


# ---------------------------------------------------------------------------
# RuntimeHealer
# ---------------------------------------------------------------------------

class RuntimeHealer:
    """
    Runs a background monitor thread.
    When a circuit breaker OPENS it:
      1. Logs the event to healer_state.json
      2. Signals the app to switch to the fallback provider
      3. Retries the probe after the timeout window
    """

    def __init__(self, services: list, poll_interval: float = 2.0):
        self.services = services
        self.poll_interval = poll_interval
        self._breakers: dict[str, CircuitBreaker] = {
            s: CircuitBreaker(s) for s in services
        }
        self._active_fallbacks: dict[str, str] = {}
        self._stop_event = threading.Event()
        self._log: list = []

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True
        )
        self._thread.start()
        print("[Healer] Monitoring started for services:", self.services)

    def stop(self) -> None:
        self._stop_event.set()

    # -- Internal monitor

    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            for service, cb in self._breakers.items():
                try:
                    state = cb.get_state_snapshot()["state"]
                    if state == State.OPEN and service not in self._active_fallbacks:
                        self._activate_fallback(service)
                    elif state == State.CLOSED and service in self._active_fallbacks:
                        self._deactivate_fallback(service)
                except Exception as exc:
                    print(f"[Healer] Monitor error for {service}: {exc}")
            time.sleep(self.poll_interval)

    def _activate_fallback(self, service: str) -> None:
        options  = FALLBACKS.get(service, [])
        fallback = options[0] if options else "degraded-mode"
        self._active_fallbacks[service] = fallback
        event = {
            "event":     "fallback_activated",
            "service":   service,
            "fallback":  fallback,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._log.append(event)
        self._persist_log()
        print(f"[Healer] FALLBACK ACTIVATED for {service} -> {fallback}")

    def _deactivate_fallback(self, service: str) -> None:
        fallback = self._active_fallbacks.pop(service, "none")
        event = {
            "event":     "fallback_deactivated",
            "service":   service,
            "fallback":  fallback,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._log.append(event)
        self._persist_log()
        print(f"[Healer] {service} recovered — fallback deactivated")

    def _persist_log(self) -> None:
        HEALER_STATE.write_text(
            json.dumps(self._log, indent=2), encoding="utf-8"
        )

    # -- Public helpers

    def get_active_provider(self, service: str) -> str:
        return self._active_fallbacks.get(service, service)

    def get_cb(self, service: str) -> CircuitBreaker:
        return self._breakers[service]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    healer = RuntimeHealer(["stripe", "twilio", "auth0", "sendgrid"])
    healer.start()
    try:
        while True:
            time.sleep(5)
            for svc, cb in healer._breakers.items():
                snap = cb.get_state_snapshot()
                print(
                    f"  [{svc}] state={snap['state']}"
                    f"  failures={snap['failures']}"
                )
    except KeyboardInterrupt:
        healer.stop()
        print("[Healer] Stopped.")
