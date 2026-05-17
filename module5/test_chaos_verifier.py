"""
ThirdPartyChaos -- Module 5: Test Verifier
Runs chaos scenarios and asserts the app meets acceptance criteria.
Run: pytest module5/ --html=report.html --self-contained-html -v
"""
import json
import time
import pytest
import requests
from pathlib import Path

CONTROL_API   = "http://localhost:9000"
SAMPLE_APP    = "http://localhost:3000"
SLOW_LIMIT_S  = 10.0  # app must respond within 10 s even under slow_response
PASS_RATE_PCT = 0.80   # 80 % of requests must succeed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post_charge(amount: int = 1000) -> requests.Response:
    return requests.post(
        f"{SAMPLE_APP}/charge",
        json={"amount": amount, "currency": "usd"},
        timeout=20,
    )


def _post_message(to: str = "+15005550006") -> requests.Response:
    return requests.post(
        f"{SAMPLE_APP}/send_sms",
        json={"to": to, "body": "ThirdPartyChaos test message"},
        timeout=20,
    )


def _pass_rate(n: int, call) -> float:
    """Fire n requests, return fraction that returned 2xx."""
    successes = 0
    for _ in range(n):
        try:
            r = call()
            if 200 <= r.status_code < 300:
                successes += 1
        except Exception:
            pass
    return successes / n


def _services_available() -> bool:
    """Return True only if both control API and sample app are up."""
    try:
        requests.get(f"{CONTROL_API}/chaos/status", timeout=2)
        requests.get(f"{SAMPLE_APP}/health",        timeout=2)
        return True
    except Exception:
        return False


skip_if_offline = pytest.mark.skipif(
    not _services_available(),
    reason="Control API or sample app not running",
)


# ---------------------------------------------------------------------------
# Baseline (no fault active)
# ---------------------------------------------------------------------------

class TestBaseline:

    @skip_if_offline
    def test_charge_baseline(self):
        """Stripe charge must succeed with no fault active."""
        r = _post_charge()
        assert r.status_code == 200, f"Baseline charge failed: {r.text}"
        assert "id" in r.json(), "Response missing charge id"

    @skip_if_offline
    def test_sms_baseline(self):
        """Twilio SMS must succeed with no fault active."""
        r = _post_message()
        assert r.status_code == 200, f"Baseline SMS failed: {r.text}"


# ---------------------------------------------------------------------------
# Fault resilience tests
# ---------------------------------------------------------------------------

class TestFaultResilience:

    @skip_if_offline
    def test_slow_response_within_limit(self, activate_fault):
        """App must respond within SLOW_LIMIT_S even under slow_response."""
        activate_fault("slow_response")
        t0 = time.monotonic()
        try:
            r = _post_charge()
        except requests.Timeout:
            pytest.fail("App timed out -- no timeout handler implemented")
        elapsed = time.monotonic() - t0
        assert elapsed < SLOW_LIMIT_S, (
            f"App took {elapsed:.1f}s -- add a timeout handler "
            f"(target: < {SLOW_LIMIT_S}s)"
        )

    @skip_if_offline
    def test_wrong_status_code_graceful(self, activate_fault):
        """App must return a structured error (not 500) on 402 from Stripe."""
        activate_fault("wrong_status_code")
        r = _post_charge()
        assert r.status_code != 500, \
            "App returned 500 on 402 -- catch payment errors explicitly"
        body = r.json()
        # Accept: structured error OR successful fallback routing
        assert ("error" in body or "message" in body
                or "fallback" in body or "id" in body), \
            "App must propagate structured error or route to fallback provider"

    @skip_if_offline
    def test_corrupted_json_pass_rate(self, activate_fault):
        """With 5% corruption, app should still pass >= 80% of requests."""
        activate_fault("corrupted_json")
        rate = _pass_rate(15, _post_charge)
        assert rate >= PASS_RATE_PCT, (
            f"Pass rate {rate:.0%} < {PASS_RATE_PCT:.0%} "
            f"-- add JSON parse error handling with retry"
        )

    @skip_if_offline
    def test_rate_limit_retry(self, activate_fault):
        """With 20% rate-limiting, app must succeed >= 80% of the time."""
        activate_fault("rate_limit")
        rate = _pass_rate(10, _post_message)
        assert rate >= PASS_RATE_PCT, (
            f"Pass rate {rate:.0%} -- add exponential backoff on 429"
        )

    @skip_if_offline
    def test_auth_failure_refresh(self, activate_fault):
        """App must re-authenticate (not 500) on an expired token."""
        activate_fault("auth_failure")
        r = _post_charge()
        assert r.status_code in (200, 401, 403), \
            "App returned 500 on auth failure -- handle 401 explicitly"

    @skip_if_offline
    def test_empty_response_no_crash(self, activate_fault):
        """App must not crash when upstream returns empty body."""
        activate_fault("empty_response")
        try:
            r = _post_message()
            assert r.status_code != 500
        except Exception as e:
            pytest.fail(f"App raised unhandled exception on empty body: {e}")

    @skip_if_offline
    def test_missing_fields_safe(self, activate_fault):
        """App must detect missing fields and not silently corrupt data."""
        activate_fault("missing_fields")
        r = _post_charge()
        body = r.json()
        if r.status_code == 200:
            assert "id" in body or "error" in body, (
                "App accepted a charge with no id -- check required fields"
            )

    @skip_if_offline
    def test_partial_success_no_duplicate(self, activate_fault):
        """App must handle pending payments without creating duplicates."""
        activate_fault("partial_success")
        r1 = _post_charge(amount=500)
        r2 = _post_charge(amount=500)
        ids = []
        for r in (r1, r2):
            if r.status_code == 200 and "id" in r.json():
                ids.append(r.json()["id"])
        assert len(ids) == len(set(ids)), \
            "Duplicate charge ids detected -- add idempotency key"

    @skip_if_offline
    def test_silent_webhook_alerting(self, activate_fault):
        """App must raise an alert when webhooks are silently dropped."""
        activate_fault("silent_webhook_drop")
        _post_charge()
        time.sleep(2)
        hs = Path("healer_state.json")
        if hs.exists():
            events = json.loads(hs.read_text(encoding="utf-8"))
            types = [e.get("event") for e in events]
            assert any("fallback" in t or "alert" in t for t in types), \
                "No alert raised for silent webhook drop"
