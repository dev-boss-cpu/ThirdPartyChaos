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

---

## Installation

```bash
# Clone the repo
git clone https://github.com/your-username/ThirdPartyChaos.git
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

Open **7 terminals** and start services in this exact order:

**Terminal 1 — Ollama**
```bash
ollama serve
```

**Terminal 2 — Mock SaaS (:8090)**
```bash
cd sample-app
source ../.venv/bin/activate        # Linux
uvicorn mock_saas:app --port 8090
```

**Terminal 3 — Proxy (:8080)**
```bash
source .venv/bin/activate
python module1/start_proxy.py --port 8080
```

**Terminal 4 — Control API (:9000)**
```bash
source .venv/bin/activate
uvicorn module2.control_api:app --port 9000
```

**Terminal 5 — Self-Healer**
```bash
source .venv/bin/activate
python module3/healer.py
```

**Terminal 6 — Sample App (:3000)**
```bash
cd sample-app
source ../.venv/bin/activate
export HTTP_PROXY=http://localhost:8080
export MOCK_SAAS_URL=http://localhost:8090
uvicorn main:app --port 3000
```

**Terminal 7 — Run Demo**
```bash
echo '{}' > module1/logs/fault_state.json
python -X utf8 live_demo.py
```

> **Windows users:** Replace `source .venv/bin/activate` with `.venv\Scripts\activate.bat` and `export VAR=value` with `set VAR=value`

---

## Demo Steps

The `live_demo.py` script runs 9 automated steps:

1. **Health Check** — verifies all services are reachable
2. **Baseline Traffic** — 4 requests with no fault active
3. **Fault Injection** — cycles all 8 active faults, 3 requests each
4. **Circuit Breaker Trip** — trips Stripe CB through full CLOSED→OPEN→HALF\_OPEN→CLOSED cycle
5. **Healer Events** — shows fallback activations from `healer_state.json`
6. **AI Repair** — Ollama generates a unified diff patch from the failure log
7. **pytest Suite** — reruns chaos tests against the live stack
8. **Forensic Report** — builds SHA-256-anchored `evidence_report.json`
9. **Deliverables Check** — confirms all output files exist

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
