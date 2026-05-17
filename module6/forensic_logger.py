"""
ThirdPartyChaos -- Module 6: Forensic Logger & Evidence Chain
Builds a cross-correlated, SHA-256-anchored evidence report from:
  - Module 1 JSONL intercept log
  - Module 3 healer state log
  - Module 4 repair patch
  - Module 5 pytest HTML report
  - Disk image checksums (optional)
  - Volatility 3 memory output (optional)
Usage: python module6/forensic_logger.py [--disk-images ...] [--memory-dump ...]
"""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT           = Path(__file__).parent.parent
INTERCEPT_LOG  = ROOT / "module1" / "logs" / "intercept.jsonl"
CHAOS_LOG      = ROOT / "module1" / "logs" / "chaos_run.jsonl"
HEALER_STATE   = ROOT / "healer_state.json"
PATCH_FILE     = ROOT / "repair.patch"
PYTEST_HTML    = ROOT / "report.html"
EVIDENCE_OUT   = ROOT / "evidence_report.json"
SHA256_FILE    = ROOT / "sha256sums.txt"
VOLATILITY_OUT = ROOT / "volatility_output.txt"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    if not path.exists():
        return "FILE_MISSING"
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def _count_injections(chaos_records: list) -> dict:
    counts: dict = {}
    for r in chaos_records:
        if r.get("event") == "injection":
            fault = r.get("fault", "unknown")
            counts[fault] = counts.get(fault, 0) + 1
    return counts


def _extract_latencies(intercept_records: list) -> dict:
    latencies = [
        r["latency_ms"] for r in intercept_records
        if r.get("event") == "response" and "latency_ms" in r
    ]
    if not latencies:
        return {}
    return {
        "count":   len(latencies),
        "min_ms":  round(min(latencies), 2),
        "max_ms":  round(max(latencies), 2),
        "avg_ms":  round(sum(latencies) / len(latencies), 2),
        "p95_ms":  round(sorted(latencies)[int(len(latencies) * 0.95)], 2),
    }


def _cross_correlate(intercept: list, chaos: list, healer: list) -> list:
    """
    Match each injection event to the nearest healer event by timestamp
    for a unified timeline.
    """
    timeline = []
    for c in chaos:
        entry = {
            "source":    "chaos_injector",
            "timestamp": c.get("timestamp"),
            "fault":     c.get("fault"),
            "url":       c.get("url"),
        }
        ct = c.get("timestamp", "")
        for h in healer:
            ht = h.get("timestamp", "")
            if abs(len(ct) - len(ht)) < 2:
                entry["healer_event"] = h.get("event")
                entry["fallback"]     = h.get("fallback")
                break
        timeline.append(entry)
    return sorted(timeline, key=lambda x: x.get("timestamp", ""))


# ---------------------------------------------------------------------------
# Disk image checksum section
# ---------------------------------------------------------------------------

def collect_disk_checksums(image_paths: list) -> list:
    """Compute SHA-256 for each disk image file."""
    results = []
    lines   = []
    for p in image_paths:
        p = Path(p)
        digest = _sha256(p)
        results.append({"file": str(p), "sha256": digest})
        lines.append(f"{digest}  {p}")
    SHA256_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results


# ---------------------------------------------------------------------------
# Volatility 3 runner
# ---------------------------------------------------------------------------

def run_volatility(memory_dump: Path,
                   search_string: str = "CLOSED") -> str:
    """Run Volatility 3 against a memory dump and grep for CB state."""
    if not memory_dump.exists():
        return f"[Forensics] Memory dump not found: {memory_dump}"
    cmd = [
        "python3", "-m", "volatility3",
        "-f", str(memory_dump),
        "linux.psaux",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        output = result.stdout + result.stderr
    except FileNotFoundError:
        output = "[Forensics] Volatility 3 not installed (pip install volatility3)"
    except subprocess.TimeoutExpired:
        output = "[Forensics] Volatility timed out after 120 s"

    hits    = [ln for ln in output.splitlines() if search_string in ln]
    summary = (
        f"[Forensics] Volatility search for '{search_string}': "
        f"{len(hits)} hit(s)\n"
    ) + "\n".join(hits)

    VOLATILITY_OUT.write_text(output, encoding="utf-8")
    return summary


# ---------------------------------------------------------------------------
# Main evidence report builder
# ---------------------------------------------------------------------------

def build_evidence_report(disk_images: list = None,
                          memory_dump: Path = None) -> dict:
    print("[M6] Loading logs...")
    intercept_records = _load_jsonl(INTERCEPT_LOG)
    chaos_records     = _load_jsonl(CHAOS_LOG)
    healer_records: list = []
    if HEALER_STATE.exists():
        try:
            healer_records = json.loads(
                HEALER_STATE.read_text(encoding="utf-8")
            )
        except Exception:
            healer_records = []

    print("[M6] Computing checksums...")
    files_to_hash = [INTERCEPT_LOG, CHAOS_LOG, HEALER_STATE, PATCH_FILE, PYTEST_HTML]
    file_hashes   = {str(p): _sha256(p) for p in files_to_hash}

    # Write sha256sums.txt
    sha_lines = [f"{v}  {k}" for k, v in file_hashes.items() if v != "FILE_MISSING"]
    SHA256_FILE.write_text("\n".join(sha_lines) + "\n", encoding="utf-8")

    disk_checksums = []
    if disk_images:
        disk_checksums = collect_disk_checksums(disk_images)

    print("[M6] Cross-correlating timeline...")
    timeline = _cross_correlate(intercept_records, chaos_records, healer_records)

    volatility_summary = ""
    if memory_dump:
        print("[M6] Running Volatility 3...")
        volatility_summary = run_volatility(Path(memory_dump))
        print(volatility_summary)

    patch_lines = 0
    if PATCH_FILE.exists():
        patch_lines = len(PATCH_FILE.read_text(encoding="utf-8").splitlines())

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool":         "ThirdPartyChaos -- Module 6 Forensic Logger",
        "summary": {
            "total_intercepted_requests": sum(
                1 for r in intercept_records if r.get("event") == "request"
            ),
            "total_error_responses": sum(
                1 for r in intercept_records
                if r.get("event") == "response"
                and str(r.get("status_code", "")).startswith(("4", "5"))
            ),
            "injections_by_fault": _count_injections(chaos_records),
            "latency_stats":       _extract_latencies(intercept_records),
            "healer_events":       len(healer_records),
            "patch_lines":         patch_lines,
        },
        "file_integrity":   file_hashes,
        "disk_images":      disk_checksums,
        "unified_timeline": timeline,
        "volatility":       volatility_summary,
    }

    EVIDENCE_OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[M6] Evidence report written to {EVIDENCE_OUT}")
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="ThirdPartyChaos M6 -- Build Evidence Report"
    )
    parser.add_argument("--disk-images", nargs="*", default=[],
                        help="Paths to disk image files for checksum")
    parser.add_argument("--memory-dump",
                        help="Path to LiME/dd memory dump for Volatility")
    args = parser.parse_args()

    report = build_evidence_report(
        disk_images=[Path(p) for p in args.disk_images],
        memory_dump=Path(args.memory_dump) if args.memory_dump else None,
    )
    print("\n[M6] Summary:")
    print(json.dumps(report["summary"], indent=2))
