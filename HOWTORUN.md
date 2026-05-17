# How to Run ThirdPartyChaos

## Before You Start

Make sure these are installed on your machine:
- Python 3.11+
- Ollama (https://ollama.com)
- The llama3.1:8b model pulled

If you haven't installed the model yet:
```
ollama pull llama3.1:8b
```

---

## Step 1 — Set Up the Virtual Environment (First Time Only)

**Windows:**
```cmd
cd C:\path\to\ThirdPartyChaos
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt
```

**Fedora Linux:**
```bash
cd /path/to/ThirdPartyChaos
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Step 2 — Reset State (Do This Every Time Before Running)

**Windows:**
```cmd
echo {} > module1\logs\fault_state.json
```

**Linux:**
```bash
echo '{}' > module1/logs/fault_state.json
```

---

## Step 3 — Open 7 Terminals and Start in This Order

> The order is critical. Do not skip ahead.

---

### Terminal 1 — Ollama (AI Engine)

```cmd
ollama serve
```

If it says "Ollama is already running" — that's fine, move on.

---

### Terminal 2 — Mock SaaS (Port 8090)

**Windows:**
```cmd
cd ThirdPartyChaos\sample-app
..\.venv\Scripts\python.exe -m uvicorn mock_saas:app --port 8090
```

**Linux:**
```bash
cd ThirdPartyChaos/sample-app
source ../.venv/bin/activate
uvicorn mock_saas:app --port 8090
```

Wait for: `Uvicorn running on http://127.0.0.1:8090`

---

### Terminal 3 — Proxy Interceptor (Port 8080)

**Windows:**
```cmd
cd ThirdPartyChaos
.venv\Scripts\python.exe module1\start_proxy.py --port 8080
```

**Linux:**
```bash
cd ThirdPartyChaos
source .venv/bin/activate
python module1/start_proxy.py --port 8080
```

Wait for: `Proxy listening on port 8080`

> You will see `Redis not available — using file-based state store` — this is normal, ignore it.

---

### Terminal 4 — Control API (Port 9000)

**Windows:**
```cmd
cd ThirdPartyChaos
.venv\Scripts\python.exe -m uvicorn module2.control_api:app --port 9000
```

**Linux:**
```bash
cd ThirdPartyChaos
source .venv/bin/activate
uvicorn module2.control_api:app --port 9000
```

Wait for: `Uvicorn running on http://127.0.0.1:9000`

---

### Terminal 5 — Self-Healer

**Windows:**
```cmd
cd ThirdPartyChaos
.venv\Scripts\python.exe module3\healer.py
```

**Linux:**
```bash
cd ThirdPartyChaos
source .venv/bin/activate
python module3/healer.py
```

Wait for: `[Healer] Monitoring started for services:`

---

### Terminal 6 — Sample App (Port 3000)

**Windows:**
```cmd
cd ThirdPartyChaos\sample-app
set HTTP_PROXY=http://localhost:8080
set MOCK_SAAS_URL=http://localhost:8090
..\.venv\Scripts\python.exe -m uvicorn main:app --port 3000
```

**Linux:**
```bash
cd ThirdPartyChaos/sample-app
source ../.venv/bin/activate
export HTTP_PROXY=http://localhost:8080
export MOCK_SAAS_URL=http://localhost:8090
uvicorn main:app --port 3000
```

Wait for: `Uvicorn running on http://127.0.0.1:3000`

---

### Terminal 7 — Run the Demo

**Windows:**
```cmd
cd ThirdPartyChaos
.venv\Scripts\python.exe -X utf8 live_demo.py
```

**Linux:**
```bash
cd ThirdPartyChaos
source .venv/bin/activate
python -X utf8 live_demo.py
```

---

## What the Demo Does (9 Steps)

| Step | Name | What You See |
|------|------|--------------|
| 1 | Health Check | All 3 services return HTTP 200 |
| 2 | Baseline Traffic | 4 clean requests — no faults |
| 3 | Fault Injection | All 8 faults injected, 3 requests each |
| 4 | Circuit Breaker Trip | Stripe CB trips CLOSED → OPEN → HALF_OPEN → CLOSED |
| 5 | Healer Events | Fallback activations shown from healer_state.json |
| 6 | AI Repair | Ollama generates a code patch — wait ~60 seconds |
| 7 | pytest Suite | 11 chaos tests run against the live stack |
| 8 | Forensic Report | SHA-256 evidence_report.json built |
| 9 | Verify Deliverables | All output files confirmed present |

> **Step 6 will pause for ~60 seconds with no output — this is normal. Ollama is thinking. Do not close anything.**

---

## Startup Order — Why It Matters

```
Ollama          → must be ready before demo Step 6 calls it
Mock SaaS       → must exist before the proxy routes traffic to it
Proxy           → must run before the Sample App connects through it
Control API     → must be up before the demo sends fault commands
Self-Healer     → must be watching before faults are injected
Sample App      → needs proxy + mock SaaS already running
Demo            → needs everything above to be healthy
```

---

## Injecting Faults Manually (Optional)

You can inject faults at any time using the Control API:

```cmd
curl -X POST http://localhost:9000/chaos/set/wrong_status_code
curl -X POST http://localhost:9000/chaos/set/auth_failure
curl -X POST http://localhost:9000/chaos/set/timeout
curl -X POST http://localhost:9000/chaos/clear
```

Available faults: `timeout`, `slow_response`, `wrong_status_code`, `corrupted_json`,
`silent_webhook_drop`, `partial_success`, `rate_limit`, `auth_failure`,
`empty_response`, `missing_fields`

---

## Running the Autonomous AI Repair (Optional)

After the demo completes, run the full autonomous loop:

```cmd
.venv\Scripts\python.exe module4\ai_repair.py sample-app/main.py --autonomous
```

This will:
1. Load failure logs
2. Call Ollama to generate a patch
3. Apply the patch to sample-app/main.py
4. Restart the sample app automatically
5. Rerun the pytest suite
6. Print verdict: `FULLY_HEALED` / `PATCH_APPLIED_TESTS_FAILING`

---

## Stopping Everything

**Windows:**
```cmd
taskkill /F /IM python.exe
```

**Linux:**
```bash
pkill -f uvicorn
pkill -f start_proxy
pkill -f healer.py
```

---

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `The system cannot find the path specified` | Wrong path to .venv | Use `..\.venv\Scripts\python.exe` from sample-app folder |
| `Redis not available` | Redis not installed | Normal — file store is used automatically |
| `Proxy listening` then crash | Pressed Ctrl+C accidentally | Rerun Terminal 3 and leave it alone |
| Step 6 times out | Ollama slow on CPU | Wait — it now has an 8 minute timeout |
| Circuit breakers stuck OPEN | State left from previous run | Run `echo {} > module1\logs\fault_state.json` and restart |
| Port already in use | Previous run still running | Run `taskkill /F /IM python.exe` first |
