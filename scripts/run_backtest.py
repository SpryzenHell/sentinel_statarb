import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "python"))

from sentinel_statarb.backtest import run


def main() -> None:
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    baseline = run(dynamic=False)
    dynamic = run(dynamic=True)
    payload = {
        "baseline": baseline.__dict__,
        "dynamic": dynamic.__dict__,
        "delta_pnl": dynamic.pnl - baseline.pnl,
        "delta_flash_crash_loss": dynamic.flash_crash_loss - baseline.flash_crash_loss,
        "claim_note": (
            "Synthetic deterministic path; values are benchmark outputs, "
            "not live-market performance."
        ),
    }
    path = out / "backtest.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
