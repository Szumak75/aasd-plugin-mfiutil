# -*- coding: UTF-8 -*-
"""
Mfiutil worker plugin runtime.

Author:  Jacek 'Szumak' Kotlarski --<szumak@virthost.pl>
Created: 2026-03-24

Purpose: Run scheduled FreeBSD `mfiutil` diagnostics for supported RAID
controllers and emit alerts for critical drive conditions.
"""

import platform
import re
import shutil
import subprocess

from datetime import datetime
from glob import glob
from threading import Event, Thread
from time import time
from typing import Any, ClassVar, Dict, List, Optional, Set, Tuple

from libs.com.message import Message
from libs.plugins import (
    NotificationScheduler,
    PluginCommonKeys,
    PluginContext,
    PluginHealth,
    PluginHealthSnapshot,
    PluginState,
    PluginStateSnapshot,
    ThPluginMixin,
)

from .config import Keys


class MfiutilRuntime(Thread, ThPluginMixin):
    """Provide the runtime responsible for mfiutil worker processing."""

    # #[CONSTANTS]####################################################################
    _CANDIDATE_PATHS: ClassVar[List[str]] = [
        "/usr/sbin/mfiutil",
        "/sbin/mfiutil",
        "/usr/bin/mfiutil",
    ]
    _CRITICAL_STATUSES: ClassVar[Set[str]] = {
        "DEGRADED",
        "FAILED",
        "MISSING",
        "OFFLINE",
        "UNCONFIGURED BAD",
    }
    _GOOD_STATUSES: ClassVar[Set[str]] = {
        "GOOD",
        "JBOD",
        "ONLINE",
        "UNCONFIGURED GOOD",
    }
    _STATUS_TOKENS: ClassVar[List[str]] = [
        "UNCONFIGURED BAD",
        "UNCONFIGURED GOOD",
        "HOT SPARE",
        "REBUILD",
        "FAILED",
        "OFFLINE",
        "MISSING",
        "DEGRADED",
        "ONLINE",
        "GOOD",
        "JBOD",
    ]

    # #[PRIVATE PROPERTIES]###########################################################
    _controller_event_cursor: ClassVar[Dict[str, int]] = {}
    _controller_event_limit_cache: ClassVar[Dict[str, int]] = {}
    _disk_status_cache: ClassVar[Dict[str, str]] = {}
    _locate_flags: ClassVar[Dict[str, bool]] = {}
    _notifications: Optional[NotificationScheduler] = None
    _battery_state_cache: ClassVar[Dict[str, str]] = {}
    _last_schedule_key: Optional[str] = None
    _rebuild_progress_cache: ClassVar[Dict[str, int]] = {}
    _tool_path: Optional[str] = None
    _volume_state_cache: ClassVar[Dict[str, str]] = {}

    # #[CONSTRUCTOR]##################################################################
    def __init__(self, context: PluginContext) -> None:
        """Initialize the mfiutil worker runtime.

        ### Arguments:
        * context: PluginContext - Plugin runtime context.
        """
        Thread.__init__(self, name=context.instance_name)
        self.daemon = True
        self._context = context
        self._health = PluginHealthSnapshot(health=PluginHealth.UNKNOWN)
        self._notifications = NotificationScheduler.from_config(context.config)
        self._state = PluginStateSnapshot(state=PluginState.CREATED)
        self._stop_event = Event()
        self._last_schedule_key = None
        self._tool_path = None

    # #[PUBLIC METHODS]################################################################
    def health(self) -> PluginHealthSnapshot:
        """Return the current health snapshot.

        ### Returns:
        PluginHealthSnapshot - Current plugin health snapshot.
        """
        health: Optional[PluginHealthSnapshot] = self._health
        if health is None:
            return PluginHealthSnapshot(
                health=PluginHealth.UNKNOWN,
                message="Health snapshot is not initialized.",
            )
        return health

    def initialize(self) -> None:
        """Prepare the runtime before startup."""
        context: Optional[PluginContext] = self._context
        notifications: Optional[NotificationScheduler] = self._notifications
        if context is None:
            self.__update_health(
                healthy=False,
                message="Plugin context is not initialized.",
            )
            self._state = PluginStateSnapshot(
                state=PluginState.FAILED,
                failure_count=1,
                message="Plugin context is not initialized.",
                stopped_at=int(time()),
            )
            return None
        if platform.system() != "FreeBSD":
            self.__update_health(
                healthy=False,
                message="The mfiutil plugin is supported only on FreeBSD.",
            )
            self._state = PluginStateSnapshot(
                state=PluginState.FAILED,
                failure_count=1,
                message="The mfiutil plugin is supported only on FreeBSD.",
                stopped_at=int(time()),
            )
            return None
        if notifications is None or not notifications.has_schedule:
            self.__update_health(
                healthy=False,
                message="AT_CHANNEL schedule is not configured.",
            )
            self._state = PluginStateSnapshot(
                state=PluginState.FAILED,
                failure_count=1,
                message="AT_CHANNEL schedule is not configured.",
                stopped_at=int(time()),
            )
            return None
        self._tool_path = self.__discover_tool_path()
        if self._tool_path is None:
            self.__update_health(
                healthy=False,
                message="Cannot locate mfiutil in the FreeBSD base system paths.",
            )
            self._state = PluginStateSnapshot(
                state=PluginState.FAILED,
                failure_count=1,
                message="Cannot locate mfiutil in the FreeBSD base system paths.",
                stopped_at=int(time()),
            )
            return None
        self._state = PluginStateSnapshot(state=PluginState.INITIALIZED)

    def run(self) -> None:
        """Run scheduled controller diagnostics through `mfiutil`."""
        context: Optional[PluginContext] = self._context
        notifications: Optional[NotificationScheduler] = self._notifications
        stop_event: Optional[Event] = self._stop_event
        if stop_event is None:
            self.__update_health(
                healthy=False,
                message="Stop event is not initialized.",
            )
            self._state = PluginStateSnapshot(
                state=PluginState.FAILED,
                failure_count=1,
                message="Stop event is not initialized.",
                stopped_at=int(time()),
            )
            return None
        if context is None or notifications is None or self._tool_path is None:
            self.__update_health(
                healthy=False,
                message="Runtime dependencies are not initialized.",
            )
            self._state = PluginStateSnapshot(
                state=PluginState.FAILED,
                failure_count=1,
                message="Runtime dependencies are not initialized.",
                stopped_at=int(time()),
            )
            return None

        self._state = PluginStateSnapshot(
            state=PluginState.RUNNING,
            started_at=int(time()),
        )
        startup_channels: List[int] = self.__startup_channels()
        if startup_channels:
            self.__run_diagnostics_pass(due_channels=startup_channels)
            self._last_schedule_key = self.__current_schedule_key(
                due_channels=notifications.due_channels()
            )
        while not stop_event.is_set():
            due_channels: List[int] = notifications.due_channels()
            schedule_key: Optional[str] = self.__current_schedule_key(
                due_channels=due_channels
            )
            if due_channels and schedule_key != self._last_schedule_key:
                self._last_schedule_key = schedule_key
                self.__run_diagnostics_pass(due_channels=due_channels)
            elif not due_channels:
                self._last_schedule_key = None
            stop_event.wait(self.__sleep_period())

        state: Optional[PluginStateSnapshot] = self._state
        self._state = PluginStateSnapshot(
            state=PluginState.STOPPED,
            started_at=state.started_at if state is not None else None,
            stopped_at=int(time()),
        )

    def start(self) -> None:
        """Start the runtime thread."""
        self._state = PluginStateSnapshot(
            state=PluginState.STARTING,
            started_at=int(time()),
        )
        Thread.start(self)

    def state(self) -> PluginStateSnapshot:
        """Return the current lifecycle snapshot.

        ### Returns:
        PluginStateSnapshot - Current plugin lifecycle snapshot.
        """
        state: Optional[PluginStateSnapshot] = self._state
        if state is None:
            return PluginStateSnapshot(
                state=PluginState.FAILED,
                failure_count=1,
                message="Lifecycle snapshot is not initialized.",
            )
        if self.is_alive() and state.state == PluginState.STARTING:
            state = PluginStateSnapshot(
                state=PluginState.RUNNING,
                started_at=state.started_at,
            )
            self._state = state
        return state

    def stop(self, timeout: Optional[float] = None) -> None:
        """Request plugin shutdown.

        ### Arguments:
        * timeout: Optional[float] - Optional join timeout.
        """
        stop_event: Optional[Event] = self._stop_event
        if stop_event is None:
            self.__update_health(
                healthy=False,
                message="Stop event is not initialized.",
            )
            self._state = PluginStateSnapshot(
                state=PluginState.FAILED,
                failure_count=1,
                message="Stop event is not initialized.",
                stopped_at=int(time()),
            )
            return None
        state: Optional[PluginStateSnapshot] = self._state
        if state is None:
            self._state = PluginStateSnapshot(
                state=PluginState.FAILED,
                failure_count=1,
                message="Lifecycle snapshot is not initialized.",
                stopped_at=int(time()),
            )
            return None
        if state.state not in (PluginState.STOPPED, PluginState.FAILED):
            self._state = PluginStateSnapshot(
                state=PluginState.STOPPING,
                started_at=state.started_at,
            )
        stop_event.set()
        if self.is_alive():
            self.join(timeout=timeout)
        state = self._state
        self._state = PluginStateSnapshot(
            state=PluginState.STOPPED,
            started_at=state.started_at if state is not None else None,
            stopped_at=int(time()),
        )

    # #[PRIVATE METHODS]###############################################################
    def __apply_locate_change(
        self,
        controller: str,
        drive: Dict[str, str],
        enable: bool,
    ) -> None:
        """Set or clear the controller locate flag for one drive.

        ### Arguments:
        * controller: str - Controller device path.
        * drive: Dict[str, str] - Parsed drive data.
        * enable: bool - `True` to enable locate, `False` to disable it.
        """
        context: Optional[PluginContext] = self._context
        if context is None:
            raise ValueError("Plugin context is not initialized.")
        drive_ref: str = drive.get("slot", "") or drive.get("id", "")
        if not drive_ref:
            context.logger.message_warning = f"Cannot change locate flag for controller '{controller}' without drive identifier."
            return None
        self.__run_mfiutil(
            controller=controller,
            args=["locate", drive_ref, "on" if enable else "off"],
        )
        key: str = self.__normalize_disk_key(controller=controller, drive=drive)
        self.__current_locate_states()[key] = enable
        context.logger.message_info = (
            f"Controller '{controller}' drive '{drive_ref}' locate set to "
            f"{'on' if enable else 'off'}."
        )

    def __build_alert_subject(
        self,
        controller: str,
        drive_label: str,
        topic: str,
    ) -> str:
        """Build a concise notification subject line.

        ### Arguments:
        * controller: str - Controller device path.
        * drive_label: str - Human-readable drive label.
        * topic: str - Alert topic.

        ### Returns:
        str - Notification subject line.
        """
        context: Optional[PluginContext] = self._context
        if context is None:
            raise ValueError("Plugin context is not initialized.")
        return f"[{context.instance_name}:{controller}:{drive_label}] {topic}"

    def __current_disk_states(self) -> Dict[str, str]:
        """Return the cached disk-state map.

        ### Returns:
        Dict[str, str] - Cached disk states.
        """
        return self._disk_status_cache

    def __current_battery_states(self) -> Dict[str, str]:
        """Return the cached battery-state map.

        ### Returns:
        Dict[str, str] - Cached battery states.
        """
        return self._battery_state_cache

    def __current_event_cursors(self) -> Dict[str, int]:
        """Return the cached per-controller event cursors.

        ### Returns:
        Dict[str, int] - Cached event sequence cursors.
        """
        return self._controller_event_cursor

    def __current_event_limits(self) -> Dict[str, int]:
        """Return the cached per-controller event query limits.

        ### Returns:
        Dict[str, int] - Cached event-count limits.
        """
        return self._controller_event_limit_cache

    def __current_locate_states(self) -> Dict[str, bool]:
        """Return the cached locate-flag state map.

        ### Returns:
        Dict[str, bool] - Cached locate-flag states.
        """
        return self._locate_flags

    def __current_rebuild_states(self) -> Dict[str, int]:
        """Return the cached rebuild-progress state map.

        ### Returns:
        Dict[str, int] - Cached rebuild progress percentages.
        """
        return self._rebuild_progress_cache

    def __current_volume_states(self) -> Dict[str, str]:
        """Return the cached controller-volume state map.

        ### Returns:
        Dict[str, str] - Cached volume states.
        """
        return self._volume_state_cache

    def __controller_unit(self, controller: str) -> int:
        """Extract the controller unit number from a device path.

        ### Arguments:
        * controller: str - Controller device path such as `/dev/mfi0`.

        ### Returns:
        int - Numeric controller unit.

        ### Raises:
        * ValueError: If the device path does not contain a supported unit number.
        """
        match: Optional[re.Match[str]] = re.match(r"^/dev/(?:mfi|mrsas)(\d+)$", controller)
        if match is None:
            raise ValueError(f"Unsupported controller device path '{controller}'.")
        return int(match.group(1))

    def __detect_controllers(self) -> List[str]:
        """Detect supported RAID controller device nodes in the system.

        ### Returns:
        List[str] - Sorted controller device paths.
        """
        controllers: List[str] = sorted(
            set(glob("/dev/mfi[0-9]*")) | set(glob("/dev/mrsas[0-9]*"))
        )
        return controllers

    def __configured_channels(self) -> List[int]:
        """Return all notification channels configured for startup delivery.

        ### Returns:
        List[int] - Unique configured dispatcher channel identifiers.
        """
        context: Optional[PluginContext] = self._context
        if context is None:
            raise ValueError("Plugin context is not initialized.")
        out: List[int] = []
        raw_channels: Any = context.config.get(PluginCommonKeys.AT_CHANNEL, [])
        if not isinstance(raw_channels, list):
            return out
        for item in raw_channels:
            channel_str: str = str(item).split(":", 1)[0].strip()
            if not channel_str:
                continue
            channel: int = int(channel_str)
            if channel not in out:
                out.append(channel)
        return out

    def __diagnose_controller(self, controller: str, due_channels: List[int]) -> bool:
        """Run one full diagnostic pass for a selected controller.

        ### Arguments:
        * controller: str - Controller device path.
        * due_channels: List[int] - Dispatcher channels currently due.

        ### Returns:
        bool - `True` when a critical condition is present after the pass.
        """
        context: Optional[PluginContext] = self._context
        if context is None:
            raise ValueError("Plugin context is not initialized.")

        adapter_output: str = self.__run_mfiutil(
            controller=controller, args=["show", "adapter"]
        )
        battery_output: str = self.__run_mfiutil(
            controller=controller, args=["show", "battery"]
        )
        config_output: str = self.__run_mfiutil(
            controller=controller, args=["show", "config"]
        )
        volumes_output: str = self.__run_mfiutil(
            controller=controller, args=["show", "volumes"]
        )
        drives_output: str = self.__run_mfiutil(
            controller=controller,
            args=["-e", "show", "drives"],
        )
        progress_output: str = self.__run_mfiutil(
            controller=controller,
            args=["-e", "show", "progress"],
        )

        adapter_summary: str = self.__parse_adapter(output=adapter_output)
        config_summary: str = self.__parse_config(output=config_output)
        if adapter_summary or config_summary:
            summary_parts: List[str] = []
            if adapter_summary:
                summary_parts.append(adapter_summary)
            if config_summary:
                summary_parts.append(f"config={config_summary}")
            context.logger.message_info = (
                f"Controller '{controller}' summary: {', '.join(summary_parts)}"
            )
        battery_info: Dict[str, str] = self.__parse_battery(output=battery_output)
        events: List[Tuple[int, str]] = self.__load_events(controller=controller)
        self.__log_battery_state(
            controller=controller,
            battery_state=battery_info["summary"],
        )
        self.__log_new_events(
            controller=controller,
            events=events,
        )

        any_critical = False
        drives: List[Dict[str, str]] = self.__parse_drives(output=drives_output)
        progress_map: Dict[str, int] = self.__parse_progress(
            controller=controller,
            output=progress_output,
        )
        disk_states: Dict[str, str] = self.__current_disk_states()
        locate_states: Dict[str, bool] = self.__current_locate_states()
        rebuild_states: Dict[str, int] = self.__current_rebuild_states()
        volume_states: Dict[str, str] = self.__current_volume_states()
        battery_states: Dict[str, str] = self.__current_battery_states()
        volumes: List[Dict[str, str]] = self.__parse_volumes(output=volumes_output)
        battery_key: str = f"{context.instance_name}:{controller}"
        battery_state: str = battery_info.get("state", "")
        previous_battery_state: Optional[str] = battery_states.get(battery_key)

        if battery_state in ("degraded", "failed"):
            any_critical = True
            if previous_battery_state != battery_state:
                self.__emit_channel_message(
                    due_channels=due_channels,
                    subject=self.__build_alert_subject(
                        controller=controller,
                        drive_label="battery",
                        topic="battery state alert",
                    ),
                    lines=[
                        f"Controller: {controller}",
                        f"Battery State: {battery_state}",
                        f"Details: {battery_info.get('summary', 'unknown')}",
                        "Action: verify battery condition and cache policy.",
                    ],
                )
        if battery_state:
            battery_states[battery_key] = battery_state

        for volume in volumes:
            volume_label: str = volume.get("id", "unknown")
            volume_key: str = f"{context.instance_name}:{controller}:{volume_label}"
            current_state: str = volume.get("state", "")
            previous_state: Optional[str] = volume_states.get(volume_key)
            if current_state and current_state != "OPTIMAL":
                any_critical = True
                if previous_state != current_state:
                    self.__emit_channel_message(
                        due_channels=due_channels,
                        subject=self.__build_alert_subject(
                            controller=controller,
                            drive_label=volume_label,
                            topic="critical volume state",
                        ),
                        lines=[
                            f"Controller: {controller}",
                            f"Volume: {volume_label}",
                            f"State: {current_state}",
                            f"Level: {volume.get('level', 'unknown')}",
                            "Action: verify array health and affected drives.",
                        ],
                    )
            if current_state:
                volume_states[volume_key] = current_state

        for drive in drives:
            current_status: str = drive.get("status", "")
            drive_label: str = drive.get("slot", "") or drive.get("id", "") or "unknown"
            disk_key: str = self.__normalize_disk_key(controller=controller, drive=drive)
            previous_status: Optional[str] = disk_states.get(disk_key)
            progress: Optional[int] = progress_map.get(disk_key)
            desired_locate: bool = current_status != "ONLINE"

            if current_status in self._CRITICAL_STATUSES:
                any_critical = True
                if previous_status != current_status:
                    self.__emit_channel_message(
                        due_channels=due_channels,
                        subject=self.__build_alert_subject(
                            controller=controller,
                            drive_label=drive_label,
                            topic="critical drive status",
                        ),
                        lines=[
                            f"Controller: {controller}",
                            f"Drive: {drive_label}",
                            f"Status: {current_status}",
                            "Action: drive replacement is required.",
                        ],
                    )
            if current_status == "REBUILD":
                if progress is not None and rebuild_states.get(disk_key) != progress:
                    self.__emit_channel_message(
                        due_channels=due_channels,
                        subject=self.__build_alert_subject(
                            controller=controller,
                            drive_label=drive_label,
                            topic="rebuild progress",
                        ),
                        lines=[
                            f"Controller: {controller}",
                            f"Drive: {drive_label}",
                            f"Status: {current_status}",
                            f"Progress: {progress}%",
                        ],
                    )
                    rebuild_states[disk_key] = progress
            else:
                rebuild_states.pop(disk_key, None)

            if previous_status is None or locate_states.get(disk_key) != desired_locate:
                self.__apply_locate_change(
                    controller=controller,
                    drive=drive,
                    enable=desired_locate,
                )

            disk_states[disk_key] = current_status

        return any_critical

    def __discover_tool_path(self) -> Optional[str]:
        """Locate `mfiutil` in standard FreeBSD base-system locations.

        ### Returns:
        Optional[str] - Resolved command path or `None`.
        """
        context: Optional[PluginContext] = self._context
        if context is None:
            raise ValueError("Plugin context is not initialized.")
        configured: str = str(context.config.get(Keys.TOOL_PATH, "")).strip()
        if configured:
            return configured
        discovered: Optional[str] = shutil.which("mfiutil")
        if discovered:
            return discovered
        for candidate in self._CANDIDATE_PATHS:
            if shutil.which(candidate):
                return candidate
        return None

    def __emit_channel_message(
        self,
        due_channels: List[int],
        subject: str,
        lines: List[str],
    ) -> None:
        """Publish one structured notification to all due channels.

        ### Arguments:
        * due_channels: List[int] - Dispatcher channels currently due.
        * subject: str - Message subject.
        * lines: List[str] - Message body lines.
        """
        context: Optional[PluginContext] = self._context
        if context is None:
            raise ValueError("Plugin context is not initialized.")
        for channel in due_channels:
            message = Message()
            message.channel = channel
            message.subject = subject
            message.messages = lines
            context.dispatcher.publish(message)
        context.logger.message_warning = " | ".join(lines)

    def __current_schedule_key(self, due_channels: List[int]) -> Optional[str]:
        """Return a deduplication key for the current scheduled minute.

        ### Arguments:
        * due_channels: List[int] - Dispatcher channels currently due.

        ### Returns:
        Optional[str] - Current schedule key or `None` when nothing is due.
        """
        if not due_channels:
            return None
        timestamp: str = datetime.now().strftime("%Y-%m-%d %H:%M")
        channels: str = ",".join(str(item) for item in sorted(due_channels))
        return f"{timestamp}:{channels}"

    def __run_diagnostics_pass(self, due_channels: List[int]) -> None:
        """Run one diagnostic pass for all detected controllers.

        ### Arguments:
        * due_channels: List[int] - Dispatcher channels used for this pass.
        """
        context: Optional[PluginContext] = self._context
        stop_event: Optional[Event] = self._stop_event
        if context is None or stop_event is None:
            raise ValueError("Runtime dependencies are not initialized.")
        controllers: List[str] = self.__detect_controllers()
        if not controllers:
            context.logger.message_warning = (
                "No supported mfi(4)/mrsas(4) controller devices found."
            )
            self.__update_health(
                healthy=False,
                message="No supported RAID controllers detected.",
            )
            return None
        any_critical: bool = False
        for controller in controllers:
            if stop_event.is_set():
                break
            try:
                if self.__diagnose_controller(
                    controller=controller,
                    due_channels=due_channels,
                ):
                    any_critical = True
            except Exception as ex:
                context.logger.message_warning = (
                    f"Controller '{controller}' diagnostic failed: {ex}"
                )
                any_critical = True
        self.__update_health(
            healthy=not any_critical,
            message=(
                "Controller diagnostics completed without critical findings."
                if not any_critical
                else "Controller diagnostics detected critical findings."
            ),
        )

    def __sleep_period(self) -> float:
        """Return the configured poll interval with a safe default.

        ### Returns:
        float - Poll interval in seconds.
        """
        context: Optional[PluginContext] = self._context
        if context is None:
            return 5.0
        raw_value: Any = context.config.get(PluginCommonKeys.SLEEP_PERIOD, 5.0)
        if isinstance(raw_value, (int, float)) and float(raw_value) > 0.0:
            return float(raw_value)
        return 5.0

    def __startup_channels(self) -> List[int]:
        """Return the channel set used for the immediate startup scan.

        ### Returns:
        List[int] - Configured dispatcher channels for the startup pass.
        """
        return self.__configured_channels()

    def __log_battery_state(self, controller: str, battery_state: str) -> None:
        """Write the battery state to plugin logs without channel notifications.

        ### Arguments:
        * controller: str - Controller device path.
        * battery_state: str - Parsed battery status summary.
        """
        context: Optional[PluginContext] = self._context
        if context is None:
            raise ValueError("Plugin context is not initialized.")
        if battery_state:
            context.logger.message_info = (
                f"Controller '{controller}' battery state: {battery_state}"
            )

    def __log_new_events(
        self,
        controller: str,
        events: List[Tuple[int, str]],
    ) -> None:
        """Log newly observed controller events since plugin startup.

        ### Arguments:
        * controller: str - Controller device path.
        * events: List[Tuple[int, str]] - Parsed controller events.
        """
        context: Optional[PluginContext] = self._context
        if context is None:
            raise ValueError("Plugin context is not initialized.")
        if not events:
            return None
        cursor_key: str = f"{context.instance_name}:{controller}"
        event_cursors: Dict[str, int] = self.__current_event_cursors()
        max_seq: int = max(item[0] for item in events)
        if cursor_key not in event_cursors:
            event_cursors[cursor_key] = max_seq
            return None
        previous: int = event_cursors[cursor_key]
        for seq, message in sorted(events, key=lambda item: item[0]):
            if seq > previous:
                context.logger.message_info = (
                    f"Controller '{controller}' new event #{seq}: {message}"
                )
        event_cursors[cursor_key] = max_seq

    def __load_events(self, controller: str) -> List[Tuple[int, str]]:
        """Load controller events with adaptive fallback for query limits.

        ### Arguments:
        * controller: str - Controller device path.

        ### Returns:
        List[Tuple[int, str]] - Parsed controller events or an empty list when
        history cannot be retrieved.
        """
        context: Optional[PluginContext] = self._context
        if context is None:
            raise ValueError("Plugin context is not initialized.")
        configured_limit: int = int(context.config[Keys.EVENT_COUNT])
        event_limits: Dict[str, int] = self.__current_event_limits()
        limit: int = event_limits.get(
            f"{context.instance_name}:{controller}",
            configured_limit,
        )
        while limit >= 1:
            try:
                events_output = self.__run_mfiutil(
                    controller=controller,
                    args=[
                        "show",
                        "events",
                        "-c",
                        "info",
                        "-n",
                        str(limit),
                    ],
                )
                event_limits[f"{context.instance_name}:{controller}"] = limit
                return self.__parse_events(output=events_output)
            except RuntimeError as ex:
                if "Event count is too high" not in str(ex):
                    context.logger.message_warning = (
                        f"Controller '{controller}' event history query failed: {ex}"
                    )
                    return []
                next_limit: Optional[int] = self.__next_event_limit(limit)
                if next_limit is None:
                    context.logger.message_warning = (
                        f"Controller '{controller}' event history query skipped: {ex}"
                    )
                    return []
                context.logger.message_warning = (
                    f"Controller '{controller}' event history limit {limit} is too high; "
                    f"retrying with {next_limit}."
                )
                limit = next_limit
        return []

    def __normalize_disk_key(self, controller: str, drive: Dict[str, str]) -> str:
        """Build a stable cache key for one controller drive entry.

        ### Arguments:
        * controller: str - Controller device path.
        * drive: Dict[str, str] - Parsed drive data.

        ### Returns:
        str - Stable cache key.
        """
        context: Optional[PluginContext] = self._context
        if context is None:
            raise ValueError("Plugin context is not initialized.")
        drive_ref: str = drive.get("slot", "") or drive.get("id", "") or drive.get("raw", "")
        return f"{context.instance_name}:{controller}:{drive_ref}"

    def __next_event_limit(self, current_limit: int) -> Optional[int]:
        """Return the next lower event limit candidate.

        ### Arguments:
        * current_limit: int - Current event-count limit.

        ### Returns:
        Optional[int] - Lower candidate limit or `None` when exhausted.
        """
        if current_limit <= 1:
            return None
        if current_limit > 10:
            next_limit: int = current_limit - 5
            if next_limit < 10:
                return 10
            return next_limit
        return current_limit - 1

    def __parse_battery(self, output: str) -> Dict[str, str]:
        """Parse the battery status from command output.

        ### Arguments:
        * output: str - Raw command output.

        ### Returns:
        Dict[str, str] - Parsed battery summary and normalized state.
        """
        normalized_output: str = output.strip()
        if normalized_output and "no battery present" in normalized_output.lower():
            return {
                "state": "not_present",
                "summary": "battery=not present",
            }

        values: Dict[str, str] = {}
        for raw_line in output.splitlines():
            line: str = raw_line.strip()
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()

        parts: List[str] = []
        if "Status" in values:
            parts.append(f"status={values['Status']}")
        if "State of Health" in values:
            parts.append(f"health={values['State of Health']}")
        if "Current Charge" in values:
            parts.append(f"charge={values['Current Charge']}")
        if "Temperature" in values:
            parts.append(f"temperature={values['Temperature']}")
        if "Next learn time" in values:
            parts.append(f"next_learn={values['Next learn time']}")

        health: str = values.get("State of Health", "").strip().lower()
        state: str = "ok"
        if health == "bad":
            state = "failed"

        return {
            "state": state,
            "summary": ", ".join(parts),
        }

    def __parse_adapter(self, output: str) -> str:
        """Parse the adapter summary from command output.

        ### Arguments:
        * output: str - Raw command output.

        ### Returns:
        str - Short adapter summary.
        """
        values: Dict[str, str] = {}
        for raw_line in output.splitlines():
            line: str = raw_line.strip()
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()

        parts: List[str] = []
        if "Product Name" in values:
            parts.append(f"product={values['Product Name']}")
        if "Firmware" in values:
            parts.append(f"firmware={values['Firmware']}")
        if "Battery Backup" in values:
            parts.append(f"battery_backup={values['Battery Backup']}")

        return ", ".join(parts)

    def __parse_config(self, output: str) -> str:
        """Parse the controller configuration summary from command output.

        ### Arguments:
        * output: str - Raw command output.

        ### Returns:
        str - Short configuration summary.
        """
        for raw_line in output.splitlines():
            line: str = raw_line.strip()
            if not line or "configuration:" not in line.lower():
                continue
            _, config = line.split(":", 1)
            return config.strip()
        return ""

    def __parse_drives(self, output: str) -> List[Dict[str, str]]:
        """Parse controller drive states from `mfiutil show drives` output.

        ### Arguments:
        * output: str - Raw command output.

        ### Returns:
        List[Dict[str, str]] - Parsed drive entries.
        """
        out: List[Dict[str, str]] = []
        for raw_line in output.splitlines():
            line: str = raw_line.strip()
            if not line:
                continue
            status: str = ""
            uppercase: str = line.upper()
            for token in self._STATUS_TOKENS:
                if token in uppercase:
                    status = token
                    break
            if not status:
                continue
            device_match: Optional[re.Match[str]]  = re.search(r"^\s*(\d+)\b", raw_line)
            slot_match: Optional[re.Match[str]] = re.search(
                r"\b(?:E\d+:)?S\d+\b|\b\d+:\d+\b", raw_line, re.IGNORECASE
            )
            out.append(
                {
                    "id": device_match.group(1) if device_match is not None else "",
                    "raw": line,
                    "slot": (
                        slot_match.group(0).upper() if slot_match is not None else ""
                    ),
                    "status": status,
                }
            )
        return out

    def __parse_events(self, output: str) -> List[Tuple[int, str]]:
        """Parse controller event-log entries from command output.

        ### Arguments:
        * output: str - Raw command output.

        ### Returns:
        List[Tuple[int, str]] - Parsed `(sequence, message)` tuples.
        """
        out: List[Tuple[int, str]] = []
        for raw_line in output.splitlines():
            line: str = raw_line.strip()
            if not line:
                continue
            match: Optional[re.Match[str]] = re.match(r"^(\d+)\s+(.*\S)\s*$", line)
            if match is None:
                continue
            out.append((int(match.group(1)), match.group(2)))
        return out

    def __parse_progress(self, controller: str, output: str) -> Dict[str, int]:
        """Parse rebuild progress data from `mfiutil show progress` output.

        ### Arguments:
        * controller: str - Controller device path.
        * output: str - Raw command output.

        ### Returns:
        Dict[str, int] - Mapping of drive identifiers to rebuild percentages.
        """
        out: Dict[str, int] = {}
        context: Optional[PluginContext] = self._context
        if context is None:
            raise ValueError("Plugin context is not initialized.")
        instance_name: str = context.instance_name
        for raw_line in output.splitlines():
            line: str = raw_line.strip()
            if not line or "rebuild" not in line.lower():
                continue
            progress_match: Optional[re.Match[str]] = re.search(r"(\d{1,3})%", line)
            if progress_match is None:
                continue
            slot_match: Optional[re.Match[str]] = re.search(
                r"\b(?:E\d+:)?S\d+\b|\b\d+:\d+\b", raw_line, re.IGNORECASE
            )
            device_match: Optional[re.Match[str]] = re.search(r"\bdrive\s+(\d+)\b", raw_line, re.IGNORECASE)
            drive_ref: str = ""
            if slot_match is not None:
                drive_ref = slot_match.group(0).upper()
            elif device_match is not None:
                drive_ref = device_match.group(1)
            if not drive_ref:
                continue
            out[f"{instance_name}:{controller}:{drive_ref}"] = int(
                progress_match.group(1)
            )
        return out

    def __parse_volumes(self, output: str) -> List[Dict[str, str]]:
        """Parse controller volume states from `mfiutil show volumes` output.

        ### Arguments:
        * output: str - Raw command output.

        ### Returns:
        List[Dict[str, str]] - Parsed volume entries.
        """
        out: List[Dict[str, str]] = []
        for raw_line in output.splitlines():
            line: str = raw_line.strip()
            if not line or line.startswith("Id ") or "Volumes:" in line:
                continue
            match: Optional[re.Match[str]] = re.match(
                r"^(mfid\d+)\s+\(\s*([^)]+)\)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)(?:\s+(.*))?$",
                line,
            )
            if match is None:
                continue
            out.append(
                {
                    "cache": match.group(6),
                    "id": match.group(1),
                    "level": match.group(3),
                    "name": (match.group(7) or "").strip(),
                    "size": match.group(2).strip(),
                    "state": match.group(5),
                    "stripe": match.group(4),
                }
            )
        return out

    def __run_mfiutil(self, controller: str, args: List[str]) -> str:
        """Run one `mfiutil` command for a selected controller.

        ### Arguments:
        * controller: str - Controller device path.
        * args: List[str] - Command arguments passed after the device selector.

        ### Returns:
        str - Command standard output.

        ### Raises:
        * RuntimeError: If the command exits with a non-zero status.
        """
        if self._tool_path is None:
            raise RuntimeError("mfiutil command path is not initialized.")
        unit: int = self.__controller_unit(controller)
        proc: subprocess.CompletedProcess[str] = subprocess.run(
            [self._tool_path, "-u", str(unit)] + args,
            capture_output=True,
            check=False,
            text=True,
        )
        if proc.returncode != 0:
            error_text: str = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
            raise RuntimeError(
                f"mfiutil command failed for controller '{controller}': {error_text}"
            )
        return proc.stdout

    def __update_health(self, healthy: bool, message: str) -> None:
        """Update the runtime health snapshot.

        ### Arguments:
        * healthy: bool - `True` when diagnostics are healthy.
        * message: str - Health summary message.
        """
        now: int = int(time())
        self._health = PluginHealthSnapshot(
            health=PluginHealth.HEALTHY if healthy else PluginHealth.DEGRADED,
            last_error_at=None if healthy else now,
            last_ok_at=now if healthy else None,
            message=message,
        )


# #[EOF]#######################################################################
