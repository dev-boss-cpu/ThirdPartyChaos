"""
ThirdPartyChaos -- Deliverable Verification Script
Run: python verify_deliverables.py
"""
from pathlib import Path

REQUIRED = [
    ("module1/logs/intercept.jsonl",          "Module 1 intercept log"),
    ("module1/logs/chaos_run.jsonl",           "Module 2 injection log"),
    ("healer_state.json",                      "Module 3 healer events"),
    ("repair.patch",                           "Module 4 AI-generated patch"),
    ("report.html",                            "Module 5 pytest HTML report"),
    ("evidence_report.json",                   "Module 6 evidence chain"),
    ("sha256sums.txt",                         "Module 6 checksums"),
    ("volatility_output.txt",                  "Module 6 Volatility output"),
    ("analysis/performance_results.json",      "Performance measurements"),
]

print("\nThirdPartyChaos -- Deliverable Check")
print("=" * 60)

ROOT   = Path(__file__).parent
all_ok = True

for rel_path, label in REQUIRED:
    p      = ROOT / rel_path
    exists = p.exists()
    size   = p.stat().st_size if exists else 0
    status = "OK" if (exists and size > 0) else "MISSING"
    if status == "MISSING":
        all_ok = False
    print(f"  [{status:7s}] {label:<42s} {rel_path}")

print()
if all_ok:
    print("All deliverables present. Ready to submit.")
else:
    print("Some deliverables are missing — see MISSING items above.")
    print("Run the full pipeline first (see README or the PDF guide).")
