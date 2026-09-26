"""Windows Task Scheduler management service for enabiz-ai."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from enabiz_ai.exceptions import ProfileError
from enabiz_ai.profiles.manager import ProfileManager

logger = logging.getLogger(__name__)

VALID_DAYS = {"sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"}
TIME_PATTERN = re.compile(r"^\d{1,2}:\d{2}$")


class SchedulerService:
    """Manages recurring weekly Windows Scheduled Tasks for profiles."""

    @staticmethod
    def validate_schedule_inputs(profile: str, day: str, time_str: str) -> None:
        """Validate scheduler parameters against security and formatting constraints.

        Raises:
            ValueError: If day or time format is invalid.
            ProfileError: If profile ID is invalid.
        """
        if day.lower() not in VALID_DAYS:
            raise ValueError(f"Invalid day: '{day}'. Valid days: {', '.join(sorted(VALID_DAYS))}")

        if not TIME_PATTERN.match(time_str):
            raise ValueError(f"Invalid time format: '{time_str}'. Expected HH:MM (e.g. 20:00)")

        if profile.lower() != "all":
            ProfileManager.validate_profile_id(profile)

    @classmethod
    def add_schedule(
        cls,
        profile: str,
        day: str,
        time_str: str,
        python_exe: str | None = None,
        cwd: Path | None = None,
    ) -> tuple[bool, str, str]:
        """Register a scheduled weekly Windows task.

        Returns:
            Tuple of (success: bool, task_name: str, message_or_error: str).
        """
        cls.validate_schedule_inputs(profile, day, time_str)

        task_name = f"ENabizAI_WeeklySync_{profile.capitalize()}"
        py_exe = python_exe or sys.executable
        working_dir = cwd or Path.cwd()
        cli_args = f"-m enabiz_ai.cli weekly --profile {profile}"

        ps_script = f"""
        $Action = New-ScheduledTaskAction -Execute '{py_exe}' -Argument '{cli_args}' -WorkingDirectory '{working_dir}'
        $Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek {day} -At {time_str}
        $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
        $Existing = Get-ScheduledTask -TaskName '{task_name}' -ErrorAction SilentlyContinue
        if ($Existing) {{ Unregister-ScheduledTask -TaskName '{task_name}' -Confirm:$false }}
        Register-ScheduledTask -TaskName '{task_name}' -Action $Action -Trigger $Trigger -Settings $Settings -Description 'Weekly e-Nabız AI task for {profile}'
        """

        res = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
        )

        if res.returncode == 0:
            return True, task_name, "Scheduled task registered successfully."
        return False, task_name, res.stderr.strip()

    @classmethod
    def list_schedules(cls) -> list[dict[str, Any]]:
        """List active e-Nabız scheduled tasks in Windows.

        Returns:
            List of dicts with TaskName and State.
        """
        ps_cmd = 'Get-ScheduledTask -TaskName "ENabizAI_*" -ErrorAction SilentlyContinue | Select-Object TaskName, State | ConvertTo-Json'
        res = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            capture_output=True,
            text=True,
        )

        if not res.stdout.strip():
            return []

        try:
            tasks = json.loads(res.stdout)
            if isinstance(tasks, dict):
                tasks = [tasks]

            state_map = {1: "Devre Dışı", 2: "Kuyrukta", 3: "Hazır (Ready)", 4: "Çalışıyor"}
            for t in tasks:
                raw_st = t.get("State", "")
                t["StateText"] = state_map.get(raw_st, str(raw_st))

            return tasks
        except (json.JSONDecodeError, KeyError):
            logger.warning("Failed to parse scheduled tasks json: %s", res.stdout)
            return []

    @classmethod
    def remove_schedule(cls, profile_or_task: str) -> tuple[bool, str]:
        """Remove a scheduled task from Windows Task Scheduler.

        Returns:
            Tuple of (success: bool, message: str).
        """
        task_name = (
            profile_or_task
            if profile_or_task.startswith("ENabizAI_")
            else f"ENabizAI_WeeklySync_{profile_or_task.capitalize()}"
        )
        ps_cmd = f'Unregister-ScheduledTask -TaskName "{task_name}" -Confirm:$false -ErrorAction SilentlyContinue'
        res = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            capture_output=True,
            text=True,
        )

        if res.returncode == 0:
            return True, task_name
        return False, res.stderr.strip()
