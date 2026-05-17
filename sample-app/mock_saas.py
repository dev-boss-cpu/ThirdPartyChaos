"""
ThirdPartyChaos -- Mock SaaS Server
Simulates Stripe, Twilio, Auth0, SendGrid endpoints for local testing.
Runs on port 8090. All requests go through the proxy (port 8080).
Start: uvicorn mock_saas:app --port 8090
"""
import uuid
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock SaaS Server", version="1.0")


# ---------------------------------------------------------------------------
# Stripe endpoints
# ---------------------------------------------------------------------------

@app.post("/stripe/v1/charges")
async def stripe_create_charge(request: Request):
    body = await request.json()
    time.sleep(0.05)  # simulate 50 ms network RTT
    return JSONResponse({
        "id":       f"ch_{uuid.uuid4().hex[:16]}",
        "object":   "charge",
        "amount":   body.get("amount", 1000),
        "currency": body.get("currency", "usd"),
        "status":   "succeeded",
        "livemode": False,
        "created":  int(time.time()),
    })


@app.get("/stripe/v1/charges/{charge_id}")
async def stripe_get_charge(charge_id: str):
    return JSONResponse({
        "id":     charge_id,
        "object": "charge",
        "status": "succeeded",
    })


# ---------------------------------------------------------------------------
# Twilio endpoints
# ---------------------------------------------------------------------------

@app.post("/twilio/2010-04-01/Accounts/TEST/Messages.json")
async def twilio_send_sms(request: Request):
    body = await request.json()
    time.sleep(0.05)
    return JSONResponse({
        "sid":          f"SM{uuid.uuid4().hex[:32]}",
        "status":       "queued",
        "to":           body.get("to", "+10000000000"),
        "body":         body.get("body", ""),
        "date_created": "2024-01-01T00:00:00Z",
    })


# ---------------------------------------------------------------------------
# Auth0 endpoints
# ---------------------------------------------------------------------------

@app.post("/auth0/oauth/token")
async def auth0_token(request: Request):
    time.sleep(0.03)
    return JSONResponse({
        "access_token": f"eyJ{uuid.uuid4().hex}",
        "token_type":   "Bearer",
        "expires_in":   86400,
    })


# ---------------------------------------------------------------------------
# SendGrid endpoints
# ---------------------------------------------------------------------------

@app.post("/sendgrid/v3/mail/send")
async def sendgrid_send(request: Request):
    time.sleep(0.03)
    return JSONResponse({"message": "success", "id": uuid.uuid4().hex},
                        status_code=202)


# ---------------------------------------------------------------------------
# Webhook (for silent_webhook_drop testing)
# ---------------------------------------------------------------------------

@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    return JSONResponse({"received": True})


# ---------------------------------------------------------------------------
# Backup provider endpoints (used by Self-Healer fallback routing)
# These bypass the chaos proxy so fallback traffic is always clean.
# ---------------------------------------------------------------------------

@app.post("/stripe-backup/v1/charges")
async def stripe_backup_charge(request: Request):
    body = await request.json()
    time.sleep(0.04)
    return JSONResponse({
        "id":       f"ch_backup_{uuid.uuid4().hex[:12]}",
        "object":   "charge",
        "amount":   body.get("amount", 1000),
        "currency": body.get("currency", "usd"),
        "status":   "succeeded",
        "provider": "stripe-backup",
        "livemode": False,
        "created":  int(time.time()),
    })


@app.post("/twilio-backup/2010-04-01/Accounts/BACKUP/Messages.json")
async def twilio_backup_sms(request: Request):
    body = await request.json()
    time.sleep(0.04)
    return JSONResponse({
        "sid":      f"SM_backup_{uuid.uuid4().hex[:28]}",
        "status":   "queued",
        "to":       body.get("to", "+10000000000"),
        "body":     body.get("body", ""),
        "provider": "vonage",
    })


@app.post("/auth0-backup/oauth/token")
async def auth0_backup_token(request: Request):
    time.sleep(0.03)
    return JSONResponse({
        "access_token": f"eyJ_backup_{uuid.uuid4().hex}",
        "token_type":   "Bearer",
        "expires_in":   86400,
        "provider":     "cognito",
    })


@app.post("/sendgrid-backup/v3/mail/send")
async def sendgrid_backup_send(request: Request):
    time.sleep(0.03)
    return JSONResponse(
        {"message": "success", "id": uuid.uuid4().hex, "provider": "mailgun"},
        status_code=202,
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "mock-saas"}
