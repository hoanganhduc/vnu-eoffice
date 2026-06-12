"""Cross-platform scheduling: cron on Linux/macOS, Task Scheduler on Windows.

`build_command()` produces the exact one-shot monitor invocation; the install
helpers register it to run every N minutes. Everything runs locally as the
current user; the normal vnu_eoffice credential lookup is used at run time.
"""
from __future__ import annotations

import platform
import shlex
import subprocess
import sys
from pathlib import Path

from . import config

TASK_NAME = "VNU-EOffice-Monitor"
CRON_TAG = "# vnu_eoffice-monitor"


def validate_interval(every_minutes: int) -> int:
    if every_minutes < 1:
        raise ValueError("--every must be at least 1 minute.")
    if every_minutes > 59 and every_minutes % 60 != 0:
        raise ValueError("--every values above 59 must be whole hours, e.g. 60 or 120.")
    return every_minutes


def build_command(monitor_args: str = "--once") -> str:
    """Absolute, cron-safe command that runs a single monitor pass."""
    py = sys.executable or "python3"
    return f"{shlex.quote(py)} -m vnu_eoffice {monitor_args}".strip()


def log_path(create: bool = True) -> Path:
    if create:
        config.ensure_dirs()
    return config.DATA_DIR / "monitor.log"


def prepare_log_file() -> Path:
    path = log_path(create=True)
    config.ensure_private_file(path)
    return path


# -- POSIX (cron) ------------------------------------------------------------
def cron_line(every_minutes: int, monitor_args: str) -> str:
    every_minutes = validate_interval(every_minutes)
    if every_minutes < 60:
        sched = f"*/{every_minutes} * * * *"
    else:
        hours = max(1, every_minutes // 60)
        sched = f"0 */{hours} * * *"
    cmd = build_command(monitor_args)
    cwd = shlex.quote(str(Path.cwd()))
    log = shlex.quote(str(log_path(create=False)))
    return f"{sched} cd {cwd} && {cmd} >> {log} 2>&1 {CRON_TAG}"


def install_cron(every_minutes: int, monitor_args: str) -> str:
    """Idempotently (re)install the crontab entry. Returns the installed line."""
    line = cron_line(every_minutes, monitor_args)
    prepare_log_file()
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
    try:
        existing_run = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    except FileNotFoundError as e:
        raise RuntimeError("`crontab` not found on this system.") from e
    existing = existing_run.stdout
    kept = [ln for ln in existing.splitlines() if CRON_TAG not in ln]
    if len(kept) == len(existing.splitlines()):
        return False
    p = subprocess.run(["crontab", "-"], input="\n".join(kept) + "\n",
                       text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"crontab remove failed: {p.stderr.strip()}")
    return True


# -- Windows (schtasks) ------------------------------------------------------
def windows_command(every_minutes: int, monitor_args: str) -> list[str]:
    every_minutes = validate_interval(every_minutes)
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


def remove_windows() -> bool:
    cmd = ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        text = (p.stderr or p.stdout).lower()
        if "cannot find" in text or "not found" in text:
            return False
        raise RuntimeError(f"schtasks delete failed: {p.stderr.strip() or p.stdout.strip()}")
    return True


# -- dispatch ----------------------------------------------------------------
def install(every_minutes: int, monitor_args: str = "--once") -> str:
    system = platform.system()
    if system == "Windows":
        return install_windows(every_minutes, monitor_args)
    return install_cron(every_minutes, monitor_args)


def remove() -> bool:
    if platform.system() == "Windows":
        return remove_windows()
    return remove_cron()


def preview(every_minutes: int, monitor_args: str = "--once") -> str:
    """Show what would be installed without changing anything."""
    if platform.system() == "Windows":
        return " ".join(windows_command(every_minutes, monitor_args))
    return cron_line(every_minutes, monitor_args)
