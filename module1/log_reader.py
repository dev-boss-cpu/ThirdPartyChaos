"""
ThirdPartyChaos -- Module 1: Log Reader
Utility to read and query intercept.jsonl and chaos_run.jsonl.
"""
import json
import argparse
from pathlib import Path
from typing import List, Optional

LOG_DIR = Path(__file__).parent / "logs"
INTERCEPT_LOG = LOG_DIR / "intercept.jsonl"
CHAOS_LOG = LOG_DIR / "chaos_run.jsonl"


# ---------------------------------------------------------------------------
# Core loader
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> List[dict]:
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


# ---------------------------------------------------------------------------
# Public API used by Modules 2, 3, 4
# ---------------------------------------------------------------------------

def load_recent_failures(limit: int = 50) -> List[dict]:
    """
    Return up to `limit` records from intercept.jsonl where the response
    status code indicates an error (4xx / 5xx) or was injected.
    """
    records = _load_jsonl(INTERCEPT_LOG)
    failures = [
        r for r in records
        if r.get("event") == "response"
        and (
            str(r.get("status_code", "")).startswith(("4", "5"))
            or r.get("injected", False)
        )
    ]
    return failures[-limit:]


def load_all_intercept() -> List[dict]:
    return _load_jsonl(INTERCEPT_LOG)


def load_chaos_log() -> List[dict]:
    return _load_jsonl(CHAOS_LOG)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli():
    parser = argparse.ArgumentParser(description="ThirdPartyChaos M1 Log Reader")
    parser.add_argument("--last", type=int, default=10, help="Show last N records")
    parser.add_argument("--errors", action="store_true", help="Show only error responses")
    parser.add_argument("--chaos", action="store_true", help="Read chaos_run.jsonl instead")
    args = parser.parse_args()

    path = CHAOS_LOG if args.chaos else INTERCEPT_LOG
    records = _load_jsonl(path)

    if args.errors:
        records = [
            r for r in records
            if r.get("event") == "response"
            and (
                str(r.get("status_code", "")).startswith(("4", "5"))
                or r.get("injected", False)
            )
        ]

    for r in records[-args.last:]:
        print(json.dumps(r, indent=2))

    print(f"\n[LogReader] Showing {min(args.last, len(records))} / {len(records)} records from {path}")


if __name__ == "__main__":
    _cli()
