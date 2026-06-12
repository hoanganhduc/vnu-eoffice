"""Cross-platform scheduling: cron on Linux/macOS, Task Scheduler on Windows.

`build_command()` produces the exact one-shot monitor invocation; the install
helpers register it to run every N minutes. Everything runs locally as the
current user; the same user's the configured local secrets file is used at run time.
"""
from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

from . import config

TASK_NAME = "VNU-EOffice-Monitor"
CRON_TAG = "# vnu_eoffice-monitor"


def build_command(monitor_args: str = "--once") -> str:
    """Absolute, cron-safe command that runs a single monitor pass."""
    py = sys.executable or "python3"
    return f'"{py}" -m vnu_eoffice {monitor_args}'.strip()


def log_path() -> Path:
    config.ensure_dirs()
    return config.DATA_DIR / "monitor.log"


# -- POSIX (cron) ------------------------------------------------------------
def cron_line(every_minutes: int, monitor_args: str) -> str:
    if every_minutes < 60:
        sched = f"*/{every_minutes} * * * *"
    else:
        hours = max(1, every_minutes // 60)
        sched = f"0 */{hours} * * *"
    cmd = build_command(monitor_args)
    return f'{sched} cd "{Path.cwd()}" && {cmd} >> "{log_path()}" 2>&1 {CRON_TAG}'


def install_cron(every_minutes: int, monitor_args: str) -> str:
    """Idempotently (re)install the crontab entry. Returns the installed line."""
    line = cron_line(every_minutes, monitor_args)
    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True,
                                  text=True).stdout
    except FileNotFoundError as e:
        raise RuntimeError("`crontab` not found on this system.") from e
    kept = [ln for ln in existing.splitlines() if CRON_TAG not in ln]
    kept.append(line)
    new = "\n".join(kept) + "\n"
    p = subprocess.run(["crontab", "-"], input=new, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"crontab install failed: {p.stderr.strip()}")
    return line


def remove_cron() -> bool:
    existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    kept = [ln for ln in existing.splitlines() if CRON_TAG not in ln]
    if len(kept) == len(existing.splitlines()):
        return False
    subprocess.run(["crontab", "-"], input="\n".join(kept) + "\n", text=True)
    return True


# -- Windows (schtasks) ------------------------------------------------------
def windows_command(every_minutes: int, monitor_args: str) -> list[str]:
    return [
        "schtasks", "/Create", "/SC", "MINUTE", "/MO", str(every_minutes),
        "/TN", TASK_NAME, "/TR", build_command(monitor_args), "/F",
    ]


def install_windows(every_minutes: int, monitor_args: str) -> str:
    cmd = windows_command(every_minutes, monitor_args)
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"schtasks failed: {p.stderr.strip() or p.stdout.strip()}")
    return " ".join(cmd)


# -- dispatch ----------------------------------------------------------------
def install(every_minutes: int, monitor_args: str = "--once") -> str:
    system = platform.system()
    if system == "Windows":
        return install_windows(every_minutes, monitor_args)
    return install_cron(every_minutes, monitor_args)


def preview(every_minutes: int, monitor_args: str = "--once") -> str:
    """Show what would be installed without changing anything."""
    if platform.system() == "Windows":
        return " ".join(windows_command(every_minutes, monitor_args))
    return cron_line(every_minutes, monitor_args)
