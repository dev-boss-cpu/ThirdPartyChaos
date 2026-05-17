"""
ThirdPartyChaos -- Sample SaaS-Dependent Application
Simulates a real app that calls Stripe, Twilio, Auth0, and SendGrid
through the ThirdPartyChaos proxy (HTTP_PROXY=http://localhost:8080).

Endpoints:
  POST /charge        -- creates a Stripe charge
  POST /send_sms      -- sends a Twilio SMS
  POST /auth          -- fetches an Auth0 token
  POST /send_email    -- sends via SendGrid
  GET  /health        -- health check

Start:
  set HTTP_PROXY=http://localhost:8080
  uvicorn main:app --port 3000 --reload
"""
import json
import os
import time
import uuid
import sys
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Config: all SaaS traffic routes via the ThirdPartyChaos proxy
# ---------------------------------------------------------------------------
PROXY_URL      = os.environ.get("HTTP_PROXY",       "http://localhost:8080")
MOCK_SAAS      = os.environ.get("MOCK_SAAS_URL",    "http://localhost:8090")
BACKUP_SAAS    = os.environ.get("BACKUP_SAAS_URL",  "http://localhost:8090")
REQUEST_TIMEOUT = float(os.environ.get("SAAS_TIMEOUT", "3.0"))

app = FastAPI(title="ThirdPartyChaos Sample App", version="1.0")

# ---------------------------------------------------------------------------
# Add sys.path for module3 circuit_breaker
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "module3"))
sys.path.insert(0, str(ROOT / "module1"))

try:
    from circuit_breaker import CircuitBreaker
    _stripe_cb  = CircuitBreaker("stripe")
    _twilio_cb  = CircuitBreaker("twilio")
    _auth0_cb   = CircuitBreaker("auth0")
    _sendgrid_cb = CircuitBreaker("sendgrid")
    CB_AVAILABLE = True
except Exception:
    CB_AVAILABLE = False


# ---------------------------------------------------------------------------
# HTTP client (routed through the proxy)
# ---------------------------------------------------------------------------

def _client() -> httpx.Client:
    # httpx 0.28+ uses proxy= (singular); older versions used proxies=
    try:
        return httpx.Client(
            proxy=PROXY_URL,
            timeout=REQUEST_TIMEOUT,
            verify=False,
            trust_env=False,
        )
    except TypeError:
        return httpx.Client(
            proxies={"http://": PROXY_URL, "https://": PROXY_URL},
            timeout=REQUEST_TIMEOUT,
            verify=False,
        )


def _backup_client() -> httpx.Client:
    """Direct client that bypasses the chaos proxy — used for fallback routing."""
    return httpx.Client(timeout=REQUEST_TIMEOUT, verify=False, trust_env=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_json(response: httpx.Response) -> dict:
    """Parse JSON safely; return error dict on parse failure."""
    try:
        return response.json()
    except Exception:
        return {
            "error":   "invalid_json",
            "message": "Upstream returned non-JSON response",
            "raw":     response.text[:200],
        }


def _idempotency_key() -> str:
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# POST /charge   (Stripe)
# ---------------------------------------------------------------------------

@app.post("/charge")
async def create_charge(request: Request):
    body = await request.json()
    amount   = body.get("amount", 1000)
    currency = body.get("currency", "usd")

    # Circuit breaker check — route to real backup provider when OPEN
    if CB_AVAILABLE and not _stripe_cb.allow_request():
        try:
            with _backup_client() as c:
                resp = c.post(f"{BACKUP_SAAS}/stripe-backup/v1/charges", json={
                    "amount": body.get("amount", 1000),
                    "currency": body.get("currency", "usd"),
                    "idempotency_key": _idempotency_key(),
                })
            data = _safe_json(resp)
            data["fallback"] = "stripe-backup"
            return JSONResponse(data, status_code=resp.status_code)
        except Exception as exc:
            return JSONResponse(
                {"error": "circuit_open", "message": "Stripe OPEN, backup also failed",
                 "detail": str(exc)},
                status_code=503,
            )

    payload = {
        "amount":   amount,
        "currency": currency,
        "idempotency_key": _idempotency_key(),
    }

    try:
        with _client() as c:
            resp = c.post(f"{MOCK_SAAS}/stripe/v1/charges", json=payload)
    except httpx.TimeoutException:
        if CB_AVAILABLE:
            _stripe_cb.record_failure()
        return JSONResponse(
            {"error": "timeout", "message": "Stripe request timed out"},
            status_code=504,
        )
    except Exception as exc:
        if CB_AVAILABLE:
            _stripe_cb.record_failure()
        return JSONResponse(
            {"error": "connection_error", "message": str(exc)},
            status_code=502,
        )

    data = _safe_json(resp)

    # Validate required fields
    if resp.status_code == 200 and "id" not in data:
        if CB_AVAILABLE:
            _stripe_cb.record_failure()
        return JSONResponse(
            {"error": "missing_fields", "message": "Stripe response missing charge id"},
            status_code=502,
        )

    if resp.status_code == 402:
        if CB_AVAILABLE:
            _stripe_cb.record_failure()
        return JSONResponse(
            {"error": "payment_required", "message": data.get("error", {}).get("message", "Payment error")},
            status_code=402,
        )

    if resp.status_code == 401:
        if CB_AVAILABLE:
            _stripe_cb.record_failure()
        return JSONResponse(
            {"error": "auth_failure", "message": "Stripe authentication failed"},
            status_code=401,
        )

    if resp.status_code >= 400:
        if CB_AVAILABLE:
            _stripe_cb.record_failure()
        return JSONResponse(
            {"error": "stripe_error", "message": str(data)},
            status_code=resp.status_code,
        )

    if CB_AVAILABLE:
        _stripe_cb.record_success()
    return JSONResponse(data)


# ---------------------------------------------------------------------------
# POST /send_sms  (Twilio)
# ---------------------------------------------------------------------------

@app.post("/send_sms")
async def send_sms(request: Request):
    body = await request.json()
    to   = body.get("to", "+15005550006")
    msg  = body.get("body", "Hello from ThirdPartyChaos")

    if CB_AVAILABLE and not _twilio_cb.allow_request():
        try:
            with _backup_client() as c:
                resp = c.post(
                    f"{BACKUP_SAAS}/twilio-backup/2010-04-01/Accounts/BACKUP/Messages.json",
                    json={"to": body.get("to", "+15005550006"),
                          "body": body.get("body", "Hello from ThirdPartyChaos")},
                )
            data = _safe_json(resp)
            data["fallback"] = "vonage"
            return JSONResponse(data, status_code=resp.status_code)
        except Exception as exc:
            return JSONResponse(
                {"error": "circuit_open", "message": "Twilio OPEN, backup also failed",
                 "detail": str(exc)},
                status_code=503,
            )

    payload = {"to": to, "body": msg}

    try:
        with _client() as c:
            resp = c.post(
                f"{MOCK_SAAS}/twilio/2010-04-01/Accounts/TEST/Messages.json",
                json=payload,
            )
    except httpx.TimeoutException:
        if CB_AVAILABLE:
            _twilio_cb.record_failure()
        return JSONResponse(
            {"error": "timeout", "message": "Twilio request timed out"},
            status_code=504,
        )
    except Exception as exc:
        if CB_AVAILABLE:
            _twilio_cb.record_failure()
        return JSONResponse({"error": "connection_error", "message": str(exc)},
                            status_code=502)

    data = _safe_json(resp)

    # Handle rate limiting with simple retry
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 1))
        time.sleep(min(retry_after, 2))  # cap at 2 s for tests
        try:
            with _client() as c:
                resp = c.post(
                    f"{MOCK_SAAS}/twilio/2010-04-01/Accounts/TEST/Messages.json",
                    json=payload,
                )
            data = _safe_json(resp)
        except Exception:
            pass

    if resp.status_code >= 400:
        if CB_AVAILABLE:
            _twilio_cb.record_failure()
        return JSONResponse(
            {"error": "twilio_error", "message": str(data)},
            status_code=resp.status_code,
        )

    if CB_AVAILABLE:
        _twilio_cb.record_success()
    return JSONResponse(data)


# ---------------------------------------------------------------------------
# POST /auth
# ---------------------------------------------------------------------------

@app.post("/auth")
async def get_token(request: Request):
    if CB_AVAILABLE and not _auth0_cb.allow_request():
        try:
            with _backup_client() as c:
                resp = c.post(f"{BACKUP_SAAS}/auth0-backup/oauth/token", json={})
            data = _safe_json(resp)
            data["fallback"] = "cognito"
            return JSONResponse(data, status_code=resp.status_code)
        except Exception as exc:
            return JSONResponse(
                {"error": "circuit_open", "message": "Auth0 OPEN, backup also failed",
                 "detail": str(exc)},
                status_code=503,
            )
    try:
        with _client() as c:
            resp = c.post(f"{MOCK_SAAS}/auth0/oauth/token", json={})
    except Exception as exc:
        if CB_AVAILABLE:
            _auth0_cb.record_failure()
        return JSONResponse({"error": str(exc)}, status_code=502)

    if resp.status_code >= 400:
        if CB_AVAILABLE:
            _auth0_cb.record_failure()
        return JSONResponse({"error": "auth0_error"}, status_code=resp.status_code)

    if CB_AVAILABLE:
        _auth0_cb.record_success()
    return JSONResponse(_safe_json(resp))


# ---------------------------------------------------------------------------
# POST /send_email
# ---------------------------------------------------------------------------

@app.post("/send_email")
async def send_email(request: Request):
    body = await request.json()
    if CB_AVAILABLE and not _sendgrid_cb.allow_request():
        try:
            with _backup_client() as c:
                resp = c.post(f"{BACKUP_SAAS}/sendgrid-backup/v3/mail/send", json=body)
            data = _safe_json(resp)
            data["fallback"] = "mailgun"
            return JSONResponse(data, status_code=resp.status_code)
        except Exception as exc:
            return JSONResponse(
                {"error": "circuit_open", "message": "SendGrid OPEN, backup also failed",
                 "detail": str(exc)},
                status_code=503,
            )
    try:
        with _client() as c:
            resp = c.post(f"{MOCK_SAAS}/sendgrid/v3/mail/send", json=body)
    except Exception as exc:
        if CB_AVAILABLE:
            _sendgrid_cb.record_failure()
        return JSONResponse({"error": str(exc)}, status_code=502)

    if resp.status_code >= 400:
        if CB_AVAILABLE:
            _sendgrid_cb.record_failure()
        return JSONResponse({"error": "sendgrid_error"}, status_code=resp.status_code)

    if CB_AVAILABLE:
        _sendgrid_cb.record_success()
    return JSONResponse(_safe_json(resp))


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    cb_states = {}
    if CB_AVAILABLE:
        for name, cb in [("stripe", _stripe_cb), ("twilio", _twilio_cb),
                          ("auth0", _auth0_cb), ("sendgrid", _sendgrid_cb)]:
            cb_states[name] = cb.get_state_snapshot()["state"]
    return {"status": "ok", "circuit_breakers": cb_states, "proxy": PROXY_URL}
