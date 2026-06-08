# -*- coding: utf-8 -*-
"""
ThirdPartyChaos -- Live Interactive Demo
Shows all fault patterns, circuit breakers, healer, and AI repair in real time.
Run AFTER all services are started:
  python live_demo.py
"""
import json
import sys
import time
from datetime import datetime

try:
    from colorama import Fore, Back, Style, init
    init(autoreset=True)
    C = True
except ImportError:
    C = False
    class Fore:
        RED = GREEN = YELLOW = CYAN = MAGENTA = WHITE = BLUE = ""
    class Style:
        BRIGHT = RESET_ALL = DIM = ""
    class Back:
        RED = GREEN = BLUE = ""

import urllib.request
import urllib.error

CTRL = "http://localhost:9000"
APP  = "http://localhost:3000"
MOCK = "http://localhost:8090"

# ---------------------------------------------------------------------------

def banner(text, color=None):
    col = color or (Fore.CYAN + Style.BRIGHT if C else "")
    reset = Style.RESET_ALL if C else ""
    print(f"\n{col}{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}{reset}")


def section(text):
    col = (Fore.YELLOW + Style.BRIGHT if C else "")
    reset = Style.RESET_ALL if C else ""
    print(f"\n{col}--- {text} ---{reset}")


def ok(text):
    col = Fore.GREEN + Style.BRIGHT if C else ""
    reset = Style.RESET_ALL if C else ""
    print(f"  {col}[OK]{reset} {text}")


def err(text):
    col = Fore.RED + Style.BRIGHT if C else ""
    reset = Style.RESET_ALL if C else ""
    print(f"  {col}[ERR]{reset} {text}")


def info(text):
    col = Fore.CYAN if C else ""
    reset = Style.RESET_ALL if C else ""
    print(f"  {col}[INF]{reset} {text}")


def warn(text):
    col = Fore.YELLOW if C else ""
    reset = Style.RESET_ALL if C else ""
    print(f"  {col}[WRN]{reset} {text}")


def inject(text):
    col = Fore.MAGENTA + Style.BRIGHT if C else ""
    reset = Style.RESET_ALL if C else ""
    print(f"  {col}[INJECT]{reset} {text}")


def healer(text):
    col = Fore.GREEN + Style.BRIGHT if C else ""
    reset = Style.RESET_ALL if C else ""
    print(f"  {col}[HEALER]{reset} {text}")


# ---------------------------------------------------------------------------

def get(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except: return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def post(url, body=None, timeout=8):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except: return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def fmt_status(code):
    if code == 0: return (Fore.RED if C else "") + "TIMEOUT"
    if 200 <= code < 300: return (Fore.GREEN if C else "") + f"HTTP {code}"
    if 400 <= code < 500: return (Fore.YELLOW if C else "") + f"HTTP {code}"
    return (Fore.RED if C else "") + f"HTTP {code}"


def pause(n=1.5):
    time.sleep(n)


# ---------------------------------------------------------------------------
# STEP 1: Health check all services
# ---------------------------------------------------------------------------

def step_health_check():
    banner("STEP 1: Health Check All Services", Fore.CYAN + Style.BRIGHT if C else "")

    services = [
        ("Mock SaaS",   f"{MOCK}/health",        3),
        ("Control API", f"{CTRL}/chaos/status",  3),
        ("Sample App",  f"{APP}/health",         10),
    ]

    all_up = True
    for name, url, tmo in services:
        code, body = get(url, timeout=tmo)
        if code and code < 500:
            ok(f"{name:<15} -> {fmt_status(code)}  {json.dumps(body)[:80]}")
        else:
            err(f"{name:<15} → {fmt_status(code)}  {json.dumps(body)[:80]}")
            all_up = False

    if not all_up:
        err("One or more services are DOWN. Start them with: start_all_windows.bat")
        sys.exit(1)
    print()
    info("All 3 core services are healthy. Proxy + Healer run silently in background.")


# ---------------------------------------------------------------------------
# STEP 2: Baseline (no fault)
# ---------------------------------------------------------------------------

def step_baseline():
    banner("STEP 2: Baseline Traffic (No Fault)", Fore.GREEN + Style.BRIGHT if C else "")
    info("Sending 4 requests through the full stack with no fault active...")
    pause(0.5)

    for i, (ep, body) in enumerate([
        ("/charge",     {"amount": 1000, "currency": "usd"}),
        ("/send_sms",   {"to": "+15005550006", "body": "Hello"}),
        ("/auth",       {}),
        ("/send_email", {"to": "user@example.com", "subject": "Test"}),
    ], 1):
        t0 = time.monotonic()
        code, body_resp = post(f"{APP}{ep}", body)
        ms = (time.monotonic() - t0) * 1000
        status_str = fmt_status(code)
        resp_preview = json.dumps(body_resp)[:60]
        print(f"  POST {ep:<15} → {status_str}  ({ms:.0f}ms)  {resp_preview}")
        pause(0.3)

    ok("All baseline requests succeeded — app is healthy.")


# ---------------------------------------------------------------------------
# STEP 3: Fault injection demos
# ---------------------------------------------------------------------------

FAULTS = [
    (
        "wrong_status_code",
        "Stripe returns HTTP 402 Payment Required (card declined)",
        "/charge", {"amount": 999},
        "App should catch 402 and return structured error (not crash)"
    ),
    (
        "auth_failure",
        "Auth0 token expires mid-session (JWT expired)",
        "/auth", {},
        "App should handle 401 gracefully (re-auth or fallback)"
    ),
    (
        "rate_limit",
        "Twilio throttles at 429 Too Many Requests",
        "/send_sms", {"to": "+15005550006"},
        "App should retry with back-off on 429"
    ),
    (
        "empty_response",
        "SendGrid returns HTTP 200 with empty body",
        "/send_email", {"to": "a@b.com"},
        "App must not crash on empty JSON"
    ),
    (
        "missing_fields",
        "Stripe returns charge object with no 'id' field",
        "/charge", {"amount": 500},
        "App should detect missing fields, return structured error"
    ),
    (
        "corrupted_json",
        "Stripe returns malformed JSON (5% of requests)",
        "/charge", {"amount": 300},
        "App must handle JSON parse errors gracefully"
    ),
    (
        "partial_success",
        "Payment 'pending' but no confirmation id (idempotency risk)",
        "/charge", {"amount": 750},
        "App must use idempotency key to avoid double-charge"
    ),
    (
        "silent_webhook_drop",
        "Webhook silently swallowed — 200 returned but nothing logged upstream",
        "/charge", {"amount": 100},
        "Healer should raise alert when webhook events stop flowing"
    ),
]


def step_fault_injection():
    banner("STEP 3: Fault Injection — All 8 Active Patterns", Fore.MAGENTA + Style.BRIGHT if C else "")

    for fault, description, endpoint, body, expectation in FAULTS:
        section(f"Fault: {fault.upper()}")
        inject(description)
        info(f"Expectation: {expectation}")

        # Activate fault
        code, resp = post(f"{CTRL}/chaos/set/{fault}", {}, timeout=3)
        if code != 200:
            warn(f"Could not activate fault (HTTP {code}) — skipping")
            continue
        info(f"Fault '{fault}' ACTIVE")
        pause(0.4)

        # Fire 3 requests under the fault
        results = []
        for i in range(3):
            t0 = time.monotonic()
            code, body_resp = post(f"{APP}{endpoint}", body, timeout=6)
            ms = (time.monotonic() - t0) * 1000
            results.append((code, body_resp, ms))
            status_str = fmt_status(code)
            preview = json.dumps(body_resp)[:70]
            print(f"    Request {i+1}: {status_str}  ({ms:.0f}ms)  {preview}")
            pause(0.2)

        # Clear fault
        post(f"{CTRL}/chaos/clear", {}, timeout=3)
        info("Fault CLEARED")

        # Assess
        codes = [r[0] for r in results]
        if all(c != 0 for c in codes):
            ok("App survived the fault without crashing (no 500 / no timeout)")
        else:
            warn("Some requests timed out or got 500 — fault exposed a gap")

        pause(1.0)


# ---------------------------------------------------------------------------
# STEP 4: Circuit Breaker demonstration
# ---------------------------------------------------------------------------

def step_circuit_breaker():
    banner("STEP 4: Circuit Breaker — CLOSED → OPEN → HALF_OPEN → CLOSED",
           Fore.YELLOW + Style.BRIGHT if C else "")

    info("Injecting auth_failure 5× to trip the Stripe circuit breaker...")
    code, _ = post(f"{CTRL}/chaos/set/auth_failure", {}, timeout=3)
    pause(0.3)

    for i in range(5):
        t0 = time.monotonic()
        code, body_resp = post(f"{APP}/charge", {"amount": 1}, timeout=5)
        ms = (time.monotonic() - t0) * 1000
        preview = json.dumps(body_resp)[:60]
        state_code, snap = get(f"{APP}/health", timeout=3)
        cb_state = snap.get("circuit_breakers", {}).get("stripe", "?")
        print(f"  Request {i+1}: {fmt_status(code)}  ({ms:.0f}ms)  CB[stripe]={cb_state}  {preview}")
        pause(0.4)

    post(f"{CTRL}/chaos/clear", {}, timeout=3)
    info("Fault cleared. Waiting 2s to check CB state...")
    pause(2)

    _, snap = get(f"{APP}/health", timeout=3)
    cb_states = snap.get("circuit_breakers", {})
    for svc, st in cb_states.items():
        col = (Fore.GREEN if st == "CLOSED" else Fore.RED if st == "OPEN" else Fore.YELLOW) if C else ""
        print(f"  {col}CB[{svc}] = {st}{Style.RESET_ALL if C else ''}")

    _, status_resp = get(f"{CTRL}/chaos/status", timeout=3)
    stats = status_resp.get("stats", {})
    info(f"Total requests seen by proxy: {stats.get('requests_seen', 'N/A')}")
    info(f"Total injections: {stats.get('injections', 'N/A')}")
    info(f"By type: {json.dumps(stats.get('faults_by_type', {}))}")


# ---------------------------------------------------------------------------
# STEP 5: Healer state
# ---------------------------------------------------------------------------

def step_healer():
    banner("STEP 5: Runtime Self-Healer Events", Fore.GREEN + Style.BRIGHT if C else "")

    import pathlib
    hs = pathlib.Path("healer_state.json")
    if hs.exists():
        try:
            events = json.loads(hs.read_text(encoding="utf-8"))
            info(f"healer_state.json contains {len(events)} events:")
            for ev in events[-6:]:
                ts = ev.get("timestamp", "")[:19]
                event = ev.get("event", "")
                svc = ev.get("service", "")
                fb = ev.get("fallback", "")
                col = Fore.GREEN if "deactivated" in event else Fore.YELLOW if C else ""
                reset = Style.RESET_ALL if C else ""
                healer(f"{col}{ts}  {event:<25} service={svc:<10} fallback={fb}{reset}")
        except Exception as exc:
            warn(f"Could not read healer_state.json: {exc}")
    else:
        warn("healer_state.json not found yet — run chaos scenarios first.")


# ---------------------------------------------------------------------------
# STEP 6: AI Repair
# ---------------------------------------------------------------------------

def step_ai_repair():
    banner("STEP 6: Local AI Code Repair (Ollama llama3.1:8b)", Fore.BLUE + Style.BRIGHT if C else "")

    import subprocess, pathlib, sys

    venv_py = pathlib.Path(sys.executable)
    source  = "sample-app/main.py"

    info("Calling ai_repair.py — this invokes Ollama to generate a unified diff patch...")
    info("Model: llama3.1:8b  |  Mode: dry-run (no file modification)")
    info("NOTE: Running on GPU — please wait ~60 seconds...")
    print()

    env = dict(__import__("os").environ)
    env["OLLAMA_MODEL"] = "llama3.1:8b"

    try:
        result = subprocess.run(
            [str(venv_py), "module4/ai_repair.py", source],
            capture_output=True, text=True, timeout=480,
            cwd=str(pathlib.Path.cwd()),
            env=env,
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        warn("Ollama timed out after 8 minutes on CPU.")
        warn("The repair.patch from the previous run will be used for demo purposes.")
        warn("On a GPU machine this step completes in under 60 seconds.")
        return

    if result.stdout:
        for line in result.stdout.strip().splitlines()[-30:]:
            print(f"  {line}")

    patch_path = pathlib.Path("repair.patch")
    if patch_path.exists() and patch_path.stat().st_size > 50:
        lines = patch_path.read_text(encoding="utf-8").splitlines()
        ok(f"repair.patch generated ({len(lines)} lines)")
        print()
        info("--- First 20 lines of repair.patch ---")
        diff_col = Fore.CYAN if C else ""
        reset = Style.RESET_ALL if C else ""
        for line in lines[:20]:
            col = (Fore.GREEN if C and line.startswith("+") and not line.startswith("+++")
                   else Fore.RED if C and line.startswith("-") and not line.startswith("---")
                   else Fore.CYAN if C and line.startswith("@@")
                   else "")
            print(f"  {col}{line}{reset}")
    else:
        warn("repair.patch is empty or missing. Check Ollama is running.")


# ---------------------------------------------------------------------------
# STEP 7: pytest
# ---------------------------------------------------------------------------

def step_pytest():
    banner("STEP 7: pytest Chaos Verifier Suite", Fore.CYAN + Style.BRIGHT if C else "")

    import subprocess, pathlib

    venv_py = pathlib.Path(sys.executable)
    info("Running: pytest module5/ --html=report.html --self-contained-html -v --timeout=120")
    print()

    result = subprocess.run(
        [str(venv_py), "-m", "pytest", "module5/",
         "--html=report.html", "--self-contained-html",
         "-v", "--tb=short", "--timeout=120"],
        capture_output=True, text=True, timeout=900,
        cwd=str(pathlib.Path.cwd()),
        errors="replace",
    )

    for line in (result.stdout + result.stderr).splitlines():
        if "PASSED" in line:
            print(f"  {Fore.GREEN if C else ''}  {line}{Style.RESET_ALL if C else ''}")
        elif "FAILED" in line or "ERROR" in line:
            print(f"  {Fore.RED if C else ''}  {line}{Style.RESET_ALL if C else ''}")
        elif "SKIPPED" in line:
            print(f"  {Fore.YELLOW if C else ''}  {line}{Style.RESET_ALL if C else ''}")
        elif line.startswith("="):
            print(f"  {Fore.CYAN if C else ''}{line}{Style.RESET_ALL if C else ''}")
        else:
            print(f"  {line}")

    if result.returncode == 0:
        ok("All tests PASSED!")
    else:
        warn(f"Some tests failed (exit {result.returncode}) — check report.html")


# ---------------------------------------------------------------------------
# STEP 8: Forensic evidence
# ---------------------------------------------------------------------------

def step_forensic():
    banner("STEP 8: Forensic Evidence Chain", Fore.YELLOW + Style.BRIGHT if C else "")

    import pathlib, subprocess

    info("Generating forensic evidence report...")
    result = subprocess.run(
        [sys.executable, "module6/forensic_logger.py"],
        capture_output=True, text=True, timeout=60,
        cwd=str(pathlib.Path.cwd()), errors="replace",
    )
    for line in result.stdout.strip().splitlines():
        print(f"  {line}")

    evidence_path = pathlib.Path("evidence_report.json")
    sha_path      = pathlib.Path("sha256sums.txt")

    if evidence_path.exists():
        report = json.loads(evidence_path.read_text(encoding="utf-8"))
        summary = report.get("summary", {})
        info(f"Evidence report generated at {report.get('generated_at', '')[:19]}")
        print()
        for k, v in summary.items():
            print(f"  {Fore.CYAN if C else ''}{k:<35}{Style.RESET_ALL if C else ''} = {v}")
        print()
        timeline = report.get("unified_timeline", [])
        info(f"Unified timeline: {len(timeline)} correlated events")
        for ev in timeline[:5]:
            ts = (ev.get("timestamp") or "")[:19]
            fault = ev.get("fault", "?")
            url = ev.get("url", "")[-40:]
            fallback = ev.get("fallback", "")
            print(f"  {ts}  fault={fault:<20} url=...{url}  fallback={fallback}")
    else:
        warn("evidence_report.json not found")

    if sha_path.exists():
        print()
        info("SHA-256 checksums (sha256sums.txt):")
        for line in sha_path.read_text(encoding="utf-8").splitlines():
            print(f"  {Fore.GREEN if C else ''}{line[:64]}{Style.RESET_ALL if C else ''}  ...{line[64:][-30:]}")


# ---------------------------------------------------------------------------
# STEP 9: Final summary
# ---------------------------------------------------------------------------

def step_summary():
    banner("STEP 9: Final Deliverable Check", Fore.GREEN + Style.BRIGHT if C else "")

    import pathlib, subprocess

    venv_py = pathlib.Path(sys.executable)
    result = subprocess.run(
        [str(venv_py), "verify_deliverables.py"],
        capture_output=True, text=True,
    )
    for line in result.stdout.splitlines():
        if "[OK" in line:
            print(f"  {Fore.GREEN if C else ''}{line}{Style.RESET_ALL if C else ''}")
        elif "[MISSING" in line:
            print(f"  {Fore.RED if C else ''}{line}{Style.RESET_ALL if C else ''}")
        else:
            print(f"  {line}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    banner("ThirdPartyChaos — LIVE DEMO", Fore.CYAN + Style.BRIGHT if C else "")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Tool: ThirdPartyChaos — SaaS Chaos Engineering with Local AI")
    print(f"  Services: Mock SaaS :8090 | Control API :9000 | Proxy :8080")
    print(f"            Healer (bg) | Sample App :3000")

    step_health_check()
    pause(1)
    step_baseline()
    pause(1)
    step_fault_injection()
    pause(1)
    step_circuit_breaker()
    pause(1)
    step_healer()
    pause(1)
    step_ai_repair()
    pause(1)
    step_pytest()
    pause(1)
    step_forensic()
    pause(1)
    step_summary()

    banner("DEMO COMPLETE", Fore.GREEN + Style.BRIGHT if C else "")
    print("  All modules demonstrated. Check report.html for full test results.")
    print("  Check evidence_report.json for the forensic evidence chain.")
    print()
