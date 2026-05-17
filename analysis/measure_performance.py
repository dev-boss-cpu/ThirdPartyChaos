"""
ThirdPartyChaos -- Performance Measurement Script
Collects:
  - Proxy interception overhead (latency delta)
  - Fault detection time (injection -> log entry)
  - MTTR (injection -> app healthy again)
  - AI patch generation time
  - Memory footprint (RSS) of each module process
  - JSONL log growth rate
Run AFTER a full chaos scenario:
  python analysis/measure_performance.py sample-app/main.py
"""
import json
import os
import sys
import time
import statistics
from datetime import datetime, timezone
from pathlib import Path

import psutil
import requests

CONTROL_API  = "http://localhost:9000"
SAMPLE_APP   = "http://localhost:3000"
ROOT         = Path(__file__).parent.parent
INTERCEPT_LOG = ROOT / "module1" / "logs" / "intercept.jsonl"
RESULTS_FILE = ROOT / "analysis" / "performance_results.json"
RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 1. Proxy overhead
# ---------------------------------------------------------------------------

def measure_proxy_overhead(n: int = 50) -> dict:
    print(f"[Perf] Measuring proxy latency over {n} requests...")
    latencies = []
    for _ in range(n):
        t0 = time.monotonic()
        try:
            requests.post(
                f"{SAMPLE_APP}/charge",
                json={"amount": 100, "currency": "usd"},
                timeout=10,
            )
        except Exception:
            pass
        latencies.append((time.monotonic() - t0) * 1000)

    if not latencies:
        return {"metric": "proxy_round_trip_ms", "error": "no responses"}

    return {
        "metric":     "proxy_round_trip_ms",
        "n":          n,
        "mean_ms":    round(statistics.mean(latencies), 2),
        "median_ms":  round(statistics.median(latencies), 2),
        "stdev_ms":   round(statistics.stdev(latencies), 2) if n > 1 else 0,
        "p95_ms":     round(sorted(latencies)[int(n * 0.95)], 2),
        "min_ms":     round(min(latencies), 2),
        "max_ms":     round(max(latencies), 2),
    }


# ---------------------------------------------------------------------------
# 2. Fault detection time
# ---------------------------------------------------------------------------

def measure_fault_detection(fault: str, n: int = 5) -> dict:
    print(f"[Perf] Measuring detection time for fault '{fault}'...")
    detection_times = []

    for _ in range(n):
        before_size = INTERCEPT_LOG.stat().st_size if INTERCEPT_LOG.exists() else 0
        t0 = time.monotonic()
        try:
            requests.post(f"{CONTROL_API}/chaos/set/{fault}", timeout=3)
        except Exception:
            continue

        try:
            requests.post(f"{SAMPLE_APP}/charge",
                          json={"amount": 100}, timeout=5)
        except Exception:
            pass

        for _ in range(100):
            time.sleep(0.05)
            current_size = INTERCEPT_LOG.stat().st_size if INTERCEPT_LOG.exists() else 0
            if current_size > before_size:
                detection_times.append((time.monotonic() - t0) * 1000)
                break

        try:
            requests.post(f"{CONTROL_API}/chaos/clear", timeout=3)
        except Exception:
            pass
        time.sleep(0.5)

    if not detection_times:
        return {"metric": "fault_detection_ms", "fault": fault, "error": "no detections"}

    return {
        "metric":   "fault_detection_ms",
        "fault":    fault,
        "n":        len(detection_times),
        "mean_ms":  round(statistics.mean(detection_times), 2),
        "min_ms":   round(min(detection_times), 2),
        "max_ms":   round(max(detection_times), 2),
    }


# ---------------------------------------------------------------------------
# 3. MTTR
# ---------------------------------------------------------------------------

def measure_mttr(fault: str) -> dict:
    print(f"[Perf] Measuring MTTR for fault '{fault}'...")
    t0 = time.monotonic()
    try:
        requests.post(f"{CONTROL_API}/chaos/set/{fault}", timeout=3)
    except Exception:
        return {"metric": "mttr_ms", "fault": fault, "error": "control API unavailable"}
    time.sleep(0.2)

    recovered = False
    for _ in range(200):
        time.sleep(0.5)
        try:
            r = requests.post(f"{SAMPLE_APP}/charge",
                              json={"amount": 100}, timeout=3)
            if 200 <= r.status_code < 300:
                recovered = True
                break
        except Exception:
            pass

    mttr_ms = (time.monotonic() - t0) * 1000
    try:
        requests.post(f"{CONTROL_API}/chaos/clear", timeout=3)
    except Exception:
        pass

    return {
        "metric":    "mttr_ms",
        "fault":     fault,
        "recovered": recovered,
        "mttr_ms":   round(mttr_ms, 2),
        "mttr_s":    round(mttr_ms / 1000, 2),
    }


# ---------------------------------------------------------------------------
# 4. AI repair time
# ---------------------------------------------------------------------------

def measure_ai_repair_time(source_file: Path) -> dict:
    print("[Perf] Measuring AI repair generation time...")
    t0 = time.monotonic()
    sys.path.insert(0, str(ROOT / "module4"))
    sys.path.insert(0, str(ROOT / "module1"))
    try:
        from ai_repair import run_repair
        result = run_repair(source_file, apply=False)
        elapsed_s = time.monotonic() - t0
        return {
            "metric":      "ai_repair_generation_s",
            "elapsed_s":   round(elapsed_s, 2),
            "patch_lines": result.get("patch_lines", 0),
            "dry_run_ok":  result.get("dry_run_ok", False),
            "status":      result.get("status", "ok"),
        }
    except Exception as exc:
        return {"metric": "ai_repair_generation_s", "error": str(exc)}


# ---------------------------------------------------------------------------
# 5. Memory footprint
# ---------------------------------------------------------------------------

def measure_memory_footprint() -> dict:
    print("[Perf] Measuring memory footprint...")
    process_rss = {}
    for proc in psutil.process_iter(["name", "memory_info"]):
        try:
            name = proc.info["name"] or ""
            for target in ("mitmdump", "redis-server", "redis", "ollama"):
                if target.lower() in name.lower():
                    rss_mb = proc.info["memory_info"].rss / (1024 * 1024)
                    process_rss[target] = round(rss_mb, 1)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return {
        "metric":          "memory_footprint",
        "process_rss_mb":  process_rss,
    }


# ---------------------------------------------------------------------------
# 6. Log growth rate
# ---------------------------------------------------------------------------

def measure_log_growth(n_requests: int = 100) -> dict:
    print(f"[Perf] Measuring log growth over {n_requests} requests...")
    before = INTERCEPT_LOG.stat().st_size if INTERCEPT_LOG.exists() else 0
    for _ in range(n_requests):
        try:
            requests.post(f"{SAMPLE_APP}/charge",
                          json={"amount": 100}, timeout=5)
        except Exception:
            pass
    after = INTERCEPT_LOG.stat().st_size if INTERCEPT_LOG.exists() else 0
    delta = after - before
    return {
        "metric":            "log_growth",
        "requests":          n_requests,
        "bytes_added":       delta,
        "bytes_per_request": round(delta / n_requests, 1) if n_requests else 0,
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all(source_file: Path) -> dict:
    results = {
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "measurements":  [],
    }

    faults_to_test = [
        "corrupted_json", "rate_limit", "wrong_status_code", "auth_failure"
    ]

    results["measurements"].append(measure_proxy_overhead(n=50))
    results["measurements"].append(measure_memory_footprint())
    results["measurements"].append(measure_log_growth(n_requests=100))

    for fault in faults_to_test:
        results["measurements"].append(measure_fault_detection(fault, n=3))
        results["measurements"].append(measure_mttr(fault))

    results["measurements"].append(measure_ai_repair_time(source_file))

    RESULTS_FILE.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n[Perf] Results saved to {RESULTS_FILE}")
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="ThirdPartyChaos -- Performance Analysis"
    )
    parser.add_argument("source_file",
                        help="Path to sample app source file")
    args = parser.parse_args()
    run_all(Path(args.source_file))
