# ThirdPartyChaos

**A Self-Healing Chaos Engineering Tool for Third-Party SaaS Dependency Resilience Using Local AI**

ThirdPartyChaos sits transparently between your application and its external SaaS providers (Stripe, Twilio, Auth0, SendGrid), injects realistic partial failure patterns sourced from real production incidents, automatically activates fallback providers via circuit breakers, and uses a locally running AI model (Ollama llama3.1:8b) to generate permanent code fixes — all without sending any data to the cloud.

---

## Architecture

```
Application  →  Proxy (:8080)  →  Mock SaaS (:8090)
                    ↓
             Failure Injector
             (10 fault patterns)
                    ↓
             Circuit Breaker ──→ Self-Healer ──→ Fallback Provider
                    ↓
             AI Repair Engine (Ollama llama3.1:8b)
                    ↓
             Test Verifier (pytest) ──→ Forensic Logger
```

---

## Modules

| Module | File | Description |
|--------|------|-------------|
| Module 1 | `module1/interceptor.py` | mitmproxy addon — intercepts every HTTP flow, logs to JSONL, dispatches chaos hooks |
| Module 2 | `module2/failure_injector.py` | 10 fault patterns; REST Control API on :9000 |
| Module 3 | `module3/circuit_breaker.py` | CLOSED → OPEN → HALF\_OPEN state machine with real fallback routing |
| Module 3 | `module3/healer.py` | Background Self-Healer thread — monitors CBs, activates fallbacks |
| Module 4 | `module4/ai_repair.py` | Ollama llama3.1:8b — generates unified diff patch from failure logs |
| Module 5 | `module5/test_chaos_verifier.py` | pytest chaos scenario verification suite |
| Module 6 | `module6/forensic_logger.py` | SHA-256-anchored forensic evidence report builder |

---

## Fault Patterns (10 total)

All fault patterns are sourced from real documented SaaS incidents (see `incidents.json`):

| # | Fault | Effect |
|---|-------|--------|
| 1 | `timeout` | Upstream hangs indefinitely |
| 2 | `slow_response` | 5–15 s artificial latency |
| 3 | `wrong_status_code` | HTTP 402 for valid requests |
| 4 | `corrupted_json` | Malformed JSON on 5% of responses |
| 5 | `silent_webhook_drop` | HTTP 200 but webhook silently lost |
| 6 | `partial_success` | Missing `id` field in charge response |
| 7 | `rate_limit` | HTTP 429 on 20% of requests |
| 8 | `auth_failure` | HTTP 401 JWT expired mid-session |
| 9 | `empty_response` | HTTP 200 with empty body |
| 10 | `missing_fields` | Critical JSON fields stripped |

---

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com/) with `llama3.1:8b` pulled
- Windows 10/11 or Fedora Linux
- [Autopsy](https://www.autopsy.com/) *(optional — for forensic disk image analysis)*
- [LiME](https://github.com/504ensicsLabs/LiME) *(optional, Linux only — for live memory acquisition)*

---

## Docker (Recommended — Zero Setup)

Everything — Python, Ollama, all services — is bundled. Your friend needs only Docker Desktop installed.

```bash
# Clone
git clone https://github.com/dev-boss-cpu/ThirdPartyChaos.git
cd ThirdPartyChaos

# Start everything (downloads llama3.1:8b ~4.9 GB on first run — one time only)
docker compose up --build

# Once all services are healthy, run the demo in a second terminal
docker compose exec app python -X utf8 live_demo.py
```

That's it. All 5 services start automatically inside the container.

**NVIDIA GPU** — uncomment the `deploy` block in `docker-compose.yml` and install the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).

**Inject faults manually from the host:**
```bash
curl -X POST http://localhost:9000/chaos/set/wrong_status_code
curl -X POST http://localhost:9000/chaos/clear
```

**Stop everything:**
```bash
docker compose down
```

---

## Installation (Manual)

```bash
# Clone the repo
git clone https://github.com/dev-boss-cpu/ThirdPartyChaos.git
cd ThirdPartyChaos

# Create virtual environment
python -m venv .venv

# Activate (Linux/Mac)
source .venv/bin/activate

# Activate (Windows CMD)
.venv\Scripts\activate.bat

# Install dependencies
pip install -r requirements.txt

# Pull Ollama model (~4.9 GB, run once)
ollama pull llama3.1:8b
```

---

## Running the Full Demo

Open **7 terminals** and start services in this **exact order**. Run the reset command every time before starting.

### Reset state (every run)

**Windows:**
```cmd
echo {} > module1\logs\fault_state.json
```
**Linux:**
```bash
echo '{}' > module1/logs/fault_state.json
```

---

**Terminal 1 — Ollama**
```bash
ollama serve
```
*(If it says "Ollama is already running" — that's fine, move on.)*

---

**Terminal 2 — Mock SaaS (:8090)**

Windows:
```cmd
cd ThirdPartyChaos\sample-app
..\.venv\Scripts\python.exe -m uvicorn mock_saas:app --port 8090
```
Linux:
```bash
cd sample-app
source ../.venv/bin/activate
uvicorn mock_saas:app --port 8090
```
Wait for: `Uvicorn running on http://127.0.0.1:8090`

---

**Terminal 3 — Proxy (:8080)**

Windows:
```cmd
.venv\Scripts\python.exe module1\start_proxy.py --port 8080
```
Linux:
```bash
source .venv/bin/activate
python module1/start_proxy.py --port 8080
```
Wait for: `Proxy listening on port 8080`
*(You will see `Redis not available — using file-based state store` — this is normal.)*

---

**Terminal 4 — Control API (:9000)**

Windows:
```cmd
.venv\Scripts\python.exe -m uvicorn module2.control_api:app --port 9000
```
Linux:
```bash
source .venv/bin/activate
uvicorn module2.control_api:app --port 9000
```
Wait for: `Uvicorn running on http://127.0.0.1:9000`

---

**Terminal 5 — Self-Healer**

Windows:
```cmd
.venv\Scripts\python.exe module3\healer.py
```
Linux:
```bash
source .venv/bin/activate
python module3/healer.py
```
Wait for: `[Healer] Monitoring started for services:`

---

**Terminal 6 — Sample App (:3000)**

Windows:
```cmd
cd ThirdPartyChaos\sample-app
set HTTP_PROXY=http://localhost:8080
set MOCK_SAAS_URL=http://localhost:8090
..\.venv\Scripts\python.exe -m uvicorn main:app --port 3000
```
Linux:
```bash
cd sample-app
source ../.venv/bin/activate
export HTTP_PROXY=http://localhost:8080
export MOCK_SAAS_URL=http://localhost:8090
uvicorn main:app --port 3000
```
Wait for: `Uvicorn running on http://127.0.0.1:3000`

---

**Terminal 7 — Run Demo**

Windows:
```cmd
.venv\Scripts\python.exe -X utf8 live_demo.py
```
Linux:
```bash
source .venv/bin/activate
python -X utf8 live_demo.py
```

> **Step 6 (AI Repair) will pause for ~60 seconds with no output — this is normal. Ollama is thinking. Do not close anything.**

---

## Demo Steps

The `live_demo.py` script runs 9 automated steps:

1. **Health Check** — verifies all 3 services return HTTP 200
2. **Baseline Traffic** — 4 clean requests with no fault active
3. **Fault Injection** — cycles 8 of the 10 fault patterns, 3 requests each (`timeout` and `slow_response` are excluded from the demo loop as they stall the pipeline)
4. **Circuit Breaker Trip** — trips Stripe CB through full CLOSED→OPEN→HALF\_OPEN→CLOSED cycle
5. **Healer Events** — shows fallback activations from `healer_state.json`
6. **AI Repair** — Ollama (`llama3.1:8b`) generates a unified diff patch from the failure log — wait ~60 seconds on GPU
7. **pytest Suite** — 11 chaos tests run against the live stack
8. **Forensic Report** — builds SHA-256-anchored `evidence_report.json`
9. **Deliverables Check** — confirms all output files are present

---

## Control API

Inject and clear faults at runtime via the Control API on port 9000:

```bash
# Activate a fault
curl -X POST http://localhost:9000/chaos/set/wrong_status_code

# Check status
curl http://localhost:9000/chaos/status

# Clear the fault
curl -X POST http://localhost:9000/chaos/clear

# List all valid faults
curl http://localhost:9000/chaos/faults
```

---

## Autonomous AI Repair

Run the full autonomous loop — detects failures, patches code, restarts app, reruns tests — with no human steps:

```bash
python module4/ai_repair.py sample-app/main.py --autonomous
```

Output verdict: `FULLY_HEALED` / `PATCH_APPLIED_TESTS_FAILING` / `PATCH_APPLIED_APP_DOWN`

---

## Output Files

After running the demo:

| File | Description |
|------|-------------|
| `module1/logs/intercept.jsonl` | Every HTTP flow logged by the proxy |
| `module1/logs/chaos_run.jsonl` | Every fault injection with real incident references |
| `healer_state.json` | Fallback activation/deactivation events |
| `repair.patch` | AI-generated unified diff patch |
| `report.html` | pytest HTML test report |
| `evidence_report.json` | SHA-256-anchored forensic evidence report |
| `sha256sums.txt` | File integrity manifest |

---

## Fedora Linux Setup

```bash
sudo dnf install -y git python3 python3-pip python3-venv redis patch
sudo systemctl enable --now redis
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b
```

---

## Domain

**Agents Unleashed** — autonomous multi-agent chaos engineering with local AI
