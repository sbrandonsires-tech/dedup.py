"""
Scheduler helper — register the pipeline as a recurring job.

Cross-platform. On Windows it prints (or installs, with --install) a
schtasks command for Windows Task Scheduler. On Linux/macOS it prints a cron
line. The original spec called for a weekly full run (Sunday 6am) plus a daily
broker-listing pull (7am); both are emitted here.

    python scheduler.py            # print scheduling instructions
    python scheduler.py --install  # Windows only: create the scheduled tasks
"""

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
PYTHON = sys.executable
MAIN = PROJECT_DIR / "main.py"

WEEKLY_TASK = "TRS_Deal_Pipeline_Weekly"
DAILY_TASK = "TRS_Deal_Pipeline_Brokers_Daily"


def _windows_commands():
    full = f'"{PYTHON}" "{MAIN}"'
    brokers = f'"{PYTHON}" "{MAIN}" --source bizbuysell'
    weekly = [
        "schtasks", "/Create", "/TN", WEEKLY_TASK, "/TR", full,
        "/SC", "WEEKLY", "/D", "SUN", "/ST", "06:00", "/F",
    ]
    daily = [
        "schtasks", "/Create", "/TN", DAILY_TASK, "/TR", brokers,
        "/SC", "DAILY", "/ST", "07:00", "/F",
    ]
    return weekly, daily


def _print_instructions():
    if sys.platform.startswith("win"):
        weekly, daily = _windows_commands()
        print("Windows Task Scheduler commands (run in an elevated prompt):\n")
        print("  " + subprocess.list2cmdline(weekly))
        print("  " + subprocess.list2cmdline(daily))
        print("\nOr run:  python scheduler.py --install")
    else:
        print("Add these lines to your crontab (`crontab -e`):\n")
        print(f"  0 6 * * 0 {PYTHON} {MAIN}")
        print(f"  0 7 * * * {PYTHON} {MAIN} --source bizbuysell")


def _install_windows():
    if not sys.platform.startswith("win"):
        print("--install is Windows-only. On Linux/macOS use the printed cron lines.")
        return
    for task in _windows_commands():
        print("Running:", subprocess.list2cmdline(task))
        subprocess.run(task, check=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TRS pipeline scheduler helper")
    parser.add_argument(
        "--install", action="store_true", help="Install scheduled tasks (Windows)"
    )
    args = parser.parse_args()
    if args.install:
        _install_windows()
    else:
        _print_instructions()
