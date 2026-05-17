"""
ThirdPartyChaos -- Module 4: Local AI Code Repair Engine
Uses Ollama (LLaMA 3.1:8b) to:
  1. Receive failure logs from Module 1
  2. Analyse root cause
  3. Generate a unified diff patch
  4. Apply the patch and verify
Usage: python module4/ai_repair.py sample-app/main.py [--apply]
"""
import json
import re
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "module1"))

import os as _os
OLLAMA_MODEL  = _os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
PATCH_OUTPUT  = ROOT / "repair.patch"
REPAIR_LOG    = ROOT / "module1" / "logs" / "repair_history.jsonl"
PROMPT_TMPL   = HERE / "prompts" / "repair_prompt.txt"


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(failures: list, source_file: Path) -> str:
    source_code = (
        source_file.read_text(errors="replace")
        if source_file.exists()
        else "(source not found)"
    )
    template = (
        PROMPT_TMPL.read_text(encoding="utf-8")
        if PROMPT_TMPL.exists()
        else textwrap.dedent("""
            You are an expert Python reliability engineer.
            Analyse the failure log and output ONLY a unified diff that adds
            defensive code (circuit breaker / retry / timeout / fallback).
            Failure log:
            {failures_json}
            Source file ({source_file_name}):
            {source_code}
            Output the unified diff now:
        """).strip()
    )
    return template.format(
        failures_json=json.dumps(failures, indent=2),
        source_file_name=source_file.name,
        source_code=source_code,
    )


# ---------------------------------------------------------------------------
# Ollama call
# ---------------------------------------------------------------------------

def _call_ollama(prompt: str) -> str:
    try:
        import ollama
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_predict": 2048},
        )
        return response["message"]["content"].strip()
    except ImportError:
        return _call_ollama_cli(prompt)
    except Exception as exc:
        print(f"[M4] Ollama API error: {exc}")
        return _call_ollama_cli(prompt)


def _call_ollama_cli(prompt: str) -> str:
    """Fallback: call ollama via subprocess."""
    try:
        result = subprocess.run(
            ["ollama", "run", OLLAMA_MODEL],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        print(f"[M4] ollama CLI error: {result.stderr}")
        return ""
    except FileNotFoundError:
        print("[M4] Ollama not installed. Install from https://ollama.com/")
        return ""
    except subprocess.TimeoutExpired:
        print("[M4] Ollama timed out after 180 s")
        return ""


# ---------------------------------------------------------------------------
# Patch extraction
# ---------------------------------------------------------------------------

def _extract_diff(raw: str) -> str:
    """Strip accidental markdown fences and find the unified diff header."""
    raw = re.sub(r"```[a-z]*\n?", "", raw)
    raw = raw.replace("```", "")
    lines = raw.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("---"):
            return "\n".join(lines[i:])
    return raw


# ---------------------------------------------------------------------------
# Apply patch (cross-platform)
# ---------------------------------------------------------------------------

def _apply_patch(patch_text: str, dry_run: bool = True) -> tuple:
    PATCH_OUTPUT.write_text(patch_text, encoding="utf-8")

    # Try GNU patch (Linux/macOS/WSL); fall back to Python-native on Windows
    patch_cmd = _find_patch_command()
    if patch_cmd:
        flags = ["--dry-run"] if dry_run else ["--forward"]
        cmd = [patch_cmd] + flags + ["-p0", "--input", str(PATCH_OUTPUT)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0, result.stdout + result.stderr
    else:
        # Pure Python dry-run validation
        if dry_run:
            has_diff_header = "---" in patch_text and "+++" in patch_text
            msg = (
                "Patch looks valid (--- / +++ headers found)."
                if has_diff_header
                else "WARNING: patch may be malformed (no --- / +++ headers)."
            )
            return has_diff_header, msg
        return False, "GNU patch not available on this system. Install via: winget install GnuWin32.Patch"


def _find_patch_command() -> str:
    for candidate in ["patch", "patch.exe"]:
        try:
            subprocess.run([candidate, "--version"],
                           capture_output=True, timeout=5)
            return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return ""


# ---------------------------------------------------------------------------
# Main repair flow
# ---------------------------------------------------------------------------

def run_repair(source_file: Path, apply: bool = False) -> dict:
    """
    Full repair pipeline:
    load failures -> build prompt -> call Ollama ->
    extract diff -> dry-run -> optionally apply
    """
    from log_reader import load_recent_failures

    print("[M4] Loading recent failures from Module 1 log...")
    failures = load_recent_failures(limit=50)
    if not failures:
        print("[M4] No failures found in log. Run a chaos scenario first.")
        return {"status": "no_failures"}

    print(f"[M4] Found {len(failures)} failure records.")
    print(f"[M4] Building prompt for {source_file.name}...")
    prompt = _build_prompt(failures, source_file)

    print(f"[M4] Calling Ollama ({OLLAMA_MODEL}) — this may take 30-90 s...")
    raw_output = _call_ollama(prompt)

    if not raw_output:
        return {"status": "ollama_unavailable"}

    print("[M4] Extracting unified diff...")
    patch_text = _extract_diff(raw_output)

    print("[M4] Running patch dry-run...")
    ok, patch_log = _apply_patch(patch_text, dry_run=True)

    result = {
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "source_file":  str(source_file),
        "failures_fed": len(failures),
        "model":        OLLAMA_MODEL,
        "patch_lines":  len(patch_text.splitlines()),
        "dry_run_ok":   ok,
        "patch_log":    patch_log,
        "patch_file":   str(PATCH_OUTPUT),
    }

    if ok and apply:
        print("[M4] Dry-run passed — applying patch...")
        ok2, log2 = _apply_patch(patch_text, dry_run=False)
        result["applied"]   = ok2
        result["apply_log"] = log2
        print("[M4] Patch applied successfully." if ok2
              else "[M4] Patch apply FAILED — check apply_log in result.")
    elif not ok:
        print("[M4] Dry-run FAILED — patch not applied. Review repair.patch.")

    REPAIR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with REPAIR_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    return result


# ---------------------------------------------------------------------------
# Autonomous agent helpers
# ---------------------------------------------------------------------------

def _kill_port(port: int) -> None:
    """Kill whichever process is listening on port (cross-platform)."""
    import signal as _signal
    if sys.platform == "win32":
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                pid = parts[-1]
                try:
                    subprocess.run(["taskkill", "/F", "/PID", pid],
                                   capture_output=True)
                    print(f"[M4-AUTO] Killed PID {pid} on port {port}")
                except Exception:
                    pass
    else:
        subprocess.run(["fuser", "-k", f"{port}/tcp"],
                       capture_output=True)


def _restart_app(port: int) -> "subprocess.Popen":
    """Kill the app on port then restart it via uvicorn."""
    import os as _os
    _kill_port(port)
    time.sleep(1.5)

    venv_py = (
        ROOT / ".venv" / "Scripts" / "python.exe"
        if sys.platform == "win32"
        else ROOT / ".venv" / "bin" / "python"
    )
    if not venv_py.exists():
        venv_py = Path(sys.executable)

    env = _os.environ.copy()
    env.setdefault("HTTP_PROXY",    "http://localhost:8080")
    env.setdefault("MOCK_SAAS_URL", "http://localhost:8090")

    proc = subprocess.Popen(
        [str(venv_py), "-m", "uvicorn", "main:app", f"--port={port}"],
        cwd=str(ROOT / "sample-app"),
        env=env,
    )
    print(f"[M4-AUTO] Sample app restarted (PID {proc.pid}) on port {port}")
    return proc


def _wait_for_health(port: int, timeout_s: int = 45) -> bool:
    """Poll /health until HTTP 200 or timeout."""
    import urllib.request as _req
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with _req.urlopen(f"http://localhost:{port}/health",
                              timeout=2) as r:
                if r.status == 200:
                    print(f"[M4-AUTO] App healthy on port {port}")
                    return True
        except Exception:
            time.sleep(1)
    print(f"[M4-AUTO] App did not become healthy within {timeout_s} s")
    return False


def _run_pytest_verification() -> dict:
    """Run module5 pytest suite; return {passed, returncode, summary}."""
    venv_py = (
        ROOT / ".venv" / "Scripts" / "python.exe"
        if sys.platform == "win32"
        else ROOT / ".venv" / "bin" / "python"
    )
    if not venv_py.exists():
        venv_py = Path(sys.executable)

    print("[M4-AUTO] Running module5 pytest verification...")
    try:
        result = subprocess.run(
            [str(venv_py), "-m", "pytest", "module5/", "-v", "--tb=short", "-q"],
            capture_output=True, text=True,
            cwd=str(ROOT),
            timeout=180,
        )
        # Extract passed/failed line
        summary = ""
        for line in reversed(result.stdout.splitlines()):
            if "passed" in line or "failed" in line or "error" in line:
                summary = line.strip()
                break
        passed = result.returncode == 0
        print(f"[M4-AUTO] pytest {'PASSED' if passed else 'FAILED'}: {summary}")
        return {
            "passed":     passed,
            "returncode": result.returncode,
            "summary":    summary,
            "output":     result.stdout[-3000:],
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "returncode": -1, "summary": "pytest timed out"}


# ---------------------------------------------------------------------------
# Autonomous repair agent
# ---------------------------------------------------------------------------

def run_autonomous_repair(source_file: Path, app_port: int = 3000) -> dict:
    """
    Full autonomous loop — zero human steps required:
      1. Load failures from intercept log
      2. Build prompt → call Ollama → extract unified diff
      3. Dry-run patch validation
      4. Apply patch to source file
      5. Kill & restart sample app
      6. Wait for /health to return 200
      7. Rerun pytest module5 verification suite
      8. Log complete result to repair_history.jsonl
    """
    print("\n[M4-AUTO] ===== Autonomous Repair Agent Started =====")

    # Steps 1-4: standard repair with apply=True
    repair_result = run_repair(source_file, apply=True)

    if repair_result.get("status") in ("no_failures", "ollama_unavailable"):
        return {**repair_result, "autonomous": False,
                "reason": repair_result.get("status")}

    if not repair_result.get("applied", False):
        print("[M4-AUTO] Patch could not be applied — aborting autonomous loop.")
        return {**repair_result, "autonomous": False, "reason": "patch_apply_failed"}

    print("[M4-AUTO] Patch applied successfully.")

    # Step 5: restart
    _proc = _restart_app(app_port)

    # Step 6: wait for health
    health_ok = _wait_for_health(app_port)

    # Step 7: rerun pytest
    pytest_result = _run_pytest_verification() if health_ok else {
        "passed": False, "summary": "skipped — app did not start"
    }

    autonomous_result = {
        **repair_result,
        "autonomous":    True,
        "app_restarted": True,
        "health_ok":     health_ok,
        "pytest":        pytest_result,
        "verdict": (
            "FULLY_HEALED"   if pytest_result.get("passed") else
            "PATCH_APPLIED_TESTS_FAILING" if health_ok else
            "PATCH_APPLIED_APP_DOWN"
        ),
    }

    # Append autonomous result to repair log
    REPAIR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with REPAIR_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(autonomous_result) + "\n")

    print(f"\n[M4-AUTO] ===== Verdict: {autonomous_result['verdict']} =====")
    return autonomous_result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ThirdPartyChaos M4 -- AI Code Repair")
    parser.add_argument("source_file",
                        help="Path to the source file to repair")
    parser.add_argument("--apply", action="store_true",
                        help="Apply the patch after a successful dry-run")
    parser.add_argument("--autonomous", action="store_true",
                        help="Full autonomous loop: patch + restart app + rerun pytest")
    args = parser.parse_args()

    if args.autonomous:
        result = run_autonomous_repair(Path(args.source_file))
    else:
        result = run_repair(Path(args.source_file), apply=args.apply)

    print("\n[M4] Result:")
    print(json.dumps(result, indent=2))
