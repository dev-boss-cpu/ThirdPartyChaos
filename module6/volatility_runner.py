"""
ThirdPartyChaos -- Module 6: Volatility Runner (standalone)
Wraps Volatility 3 for memory forensics of the chaos run.
Usage: python module6/volatility_runner.py --dump /tmp/memory.lime
"""
import argparse
import subprocess
from pathlib import Path

ROOT           = Path(__file__).parent.parent
VOLATILITY_OUT = ROOT / "volatility_output.txt"


def run(dump: Path, search: str = "CLOSED") -> str:
    from forensic_logger import run_volatility
    summary = run_volatility(dump, search_string=search)
    print(summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ThirdPartyChaos M6 -- Volatility Runner"
    )
    parser.add_argument("--dump", required=True, help="Path to memory dump file")
    parser.add_argument("--search", default="CLOSED",
                        help="String to search for in memory (default: CLOSED)")
    args = parser.parse_args()
    run(Path(args.dump), search=args.search)
