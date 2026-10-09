"""The kill switch: a file that, while it exists, blocks every new trade.

    python -m trader.risk.killswitch status
    python -m trader.risk.killswitch engage "why"
    python -m trader.risk.killswitch release        # deliberately manual

The risk engine engages it automatically on a drawdown breach. Only a person can release it; no
strategy, AI output or Telegram message can.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from trader.config import ROOT

KILL_FILE = ROOT / "state" / "KILL_SWITCH"


class KillSwitch:
    def __init__(self, path: Path = KILL_FILE):
        self.path = Path(path)

    @property
    def engaged(self) -> bool:
        return self.path.exists()

    @property
    def reason(self) -> str:
        return self.path.read_text(encoding="utf-8").strip() if self.engaged else ""

    def engage(self, reason: str) -> None:
        if not self.engaged:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(f"{datetime.now():%Y-%m-%d %H:%M:%S} {reason}\n", encoding="utf-8")

    def release(self) -> None:
        self.path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Inspect, engage or release the kill switch.")
    parser.add_argument("command", choices=["status", "engage", "release"])
    parser.add_argument("reason", nargs="?", default="engaged by hand")
    args = parser.parse_args(argv)
    switch = KillSwitch(KILL_FILE)
    if args.command == "engage":
        switch.engage(args.reason)
    elif args.command == "release":
        switch.release()
    print(f"Kill switch {'ENGAGED: ' + switch.reason if switch.engaged else 'released'}")


if __name__ == "__main__":
    main()
