# -*- coding: UTF-8 -*-
"""
Author:  Jacek 'Szumak' Kotlarski --<szumak@virthost.pl>
Created: 2026-03-25

Purpose: Provide regression coverage for the standalone mfiutil plugin runtime.
"""

import importlib.util
import sys
import unittest

from pathlib import Path
from queue import Queue
from types import ModuleType
from typing import List
from unittest.mock import MagicMock, patch

from jsktoolbox.configtool import Config as ConfigTool
from jsktoolbox.logstool import LoggerClient, LoggerQueue

from libs import AppName
from libs.com.message import ThDispatcher
from libs.plugins import DispatcherAdapter, PluginContext


def _load_plugin_spec():
    """Load `get_plugin_spec()` using the same package semantics as the host."""
    repo_root = Path(__file__).resolve().parents[1]
    package_name = "aasd_plugin_mfiutil"
    package_module = ModuleType(package_name)
    package_module.__file__ = str((repo_root / "__init__.py").resolve())
    package_module.__package__ = package_name
    package_module.__path__ = [str(repo_root)]
    sys.modules[package_name] = package_module

    module_name = f"{package_name}.load"
    spec = importlib.util.spec_from_file_location(module_name, repo_root / "load.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot build plugin spec loader.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.get_plugin_spec


class _RecordingLogger:
    """Collect assigned log messages for assertion-friendly tests."""

    # #[CONSTRUCTOR]##################################################################
    def __init__(self) -> None:
        """Initialize empty log-message buffers."""
        self.info_messages: List[str] = []
        self.warning_messages: List[str] = []

    # #[PUBLIC PROPERTIES]############################################################
    @property
    def message_info(self) -> str:
        """Return the most recent info message."""
        if not self.info_messages:
            return ""
        return self.info_messages[-1]

    @message_info.setter
    def message_info(self, value: str) -> None:
        """Store one info message."""
        self.info_messages.append(value)

    @property
    def message_warning(self) -> str:
        """Return the most recent warning message."""
        if not self.warning_messages:
            return ""
        return self.warning_messages[-1]

    @message_warning.setter
    def message_warning(self, value: str) -> None:
        """Store one warning message."""
        self.warning_messages.append(value)


class TestMfiutilRuntime(unittest.TestCase):
    """Cover the standalone mfiutil runtime behavior."""

    # #[CONSTRUCTOR]##################################################################
    def setUp(self) -> None:
        """Reset class-level caches before each test."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        MfiutilRuntime._battery_state_cache = {}
        MfiutilRuntime._controller_event_cursor = {}
        MfiutilRuntime._controller_event_limit_cache = {}
        MfiutilRuntime._disk_status_cache = {}
        MfiutilRuntime._locate_flags = {}
        MfiutilRuntime._rebuild_progress_cache = {}
        MfiutilRuntime._volume_state_cache = {}

    # #[PRIVATE METHODS]###############################################################
    def __build_context(self, instance_name: str) -> PluginContext:
        """Build a minimal plugin context for runtime tests.

        ### Arguments:
        * instance_name: str - Runtime instance name.

        ### Returns:
        PluginContext - Minimal context object accepted by the runtime factory.
        """
        qlog = LoggerQueue()
        qcom: Queue = Queue()
        dispatcher = ThDispatcher(
            qlog=qlog,
            qcom=qcom,
            debug=False,
            verbose=False,
        )
        adapter = DispatcherAdapter(qcom=qcom, dispatcher=dispatcher)
        return PluginContext(
            app_meta=AppName(app_name="AASd", app_version="2.4.5-DEV"),
            config={},
            config_handler=ConfigTool("/tmp/unused.conf", "AASd", auto_create=True),
            debug=False,
            dispatcher=adapter,
            instance_name=instance_name,
            logger=LoggerClient(queue=qlog, name=instance_name),
            plugin_id=f"test.{instance_name}",
            plugin_kind="worker",
            qlog=qlog,
            verbose=False,
        )

    # #[PUBLIC METHODS]################################################################
    def test_01_should_import_plugin_spec_from_load_module(self) -> None:
        """Load the plugin spec through the entry-point module."""
        get_plugin_spec = _load_plugin_spec()
        plugin_spec = get_plugin_spec()

        self.assertEqual(plugin_spec.plugin_id, "mfiutil.worker")
        self.assertEqual(plugin_spec.plugin_name, "plugin_mfiutil")

    def test_02_should_discover_mfiutil_path_from_base_system_candidates(self) -> None:
        """Discover `mfiutil` through the expected FreeBSD search flow."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_path")
        context.config = {
            "at_channel": ["1:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "",
        }
        runtime = MfiutilRuntime(context)

        with patch("plugins.mfiutil.plugin.runtime.platform.system", return_value="FreeBSD"):
            with patch(
                "plugins.mfiutil.plugin.runtime.shutil.which",
                side_effect=[None, "/usr/sbin/mfiutil", None, None],
            ):
                runtime.initialize()

        self.assertEqual(runtime.state().state, "initialized")

    def test_02a_should_detect_multiple_controller_device_nodes(self) -> None:
        """Detect multiple controller devices from `/dev/mfi*` and `/dev/mrsas*`."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_detect")
        context.config = {
            "at_channel": ["1:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)

        with patch(
            "plugins.mfiutil.plugin.runtime.glob",
            side_effect=[
                ["/dev/mfi1", "/dev/mfi0"],
                ["/dev/mrsas2"],
            ],
        ):
            controllers = runtime._MfiutilRuntime__detect_controllers()

        self.assertEqual(controllers, ["/dev/mfi0", "/dev/mfi1", "/dev/mrsas2"])

    def test_02b_should_build_commands_with_unit_selector(self) -> None:
        """Build all controller commands with `-u <unit>` instead of `-D`."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_unit")
        context.config = {
            "at_channel": ["1:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)
        runtime._tool_path = "/usr/sbin/mfiutil"
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "adapter output"

        with patch(
            "plugins.mfiutil.plugin.runtime.subprocess.run",
            return_value=proc,
        ) as run_mock:
            output = runtime._MfiutilRuntime__run_mfiutil(
                controller="/dev/mfi2",
                args=["show", "adapter"],
            )

        self.assertEqual(output, "adapter output")
        run_mock.assert_called_once_with(
            ["/usr/sbin/mfiutil", "-u", "2", "show", "adapter"],
            capture_output=True,
            check=False,
            text=True,
        )

    def test_03_should_parse_drive_and_progress_outputs(self) -> None:
        """Parse drive states and rebuild progress from synthetic output."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_parse")
        context.config = {
            "at_channel": ["1:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)

        drives = runtime._MfiutilRuntime__parse_drives(
            "0 E1:S2 FAILED drive failed\n1 E1:S3 REBUILD drive rebuilding\n"
        )
        progress = runtime._MfiutilRuntime__parse_progress(
            controller="/dev/mfi0",
            output="E1:S3 rebuild is 45% complete\n",
        )

        self.assertEqual(drives[0]["slot"], "E1:S2")
        self.assertEqual(drives[0]["status"], "FAILED")
        self.assertEqual(progress["mfiutil_parse:/dev/mfi0:E1:S3"], 45)

    def test_03_should_parse_volume_states_from_table_output(self) -> None:
        """Parse volume rows from realistic `show volumes` output."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_volumes")
        context.config = {
            "at_channel": ["1:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)

        volumes = runtime._MfiutilRuntime__parse_volumes(
            """
/dev/mfi0 Volumes:
  Id     Size    Level   Stripe  State   Cache   Name
 mfid0 (   68G) RAID-1      64K OPTIMAL Disabled
 mfid1 (   18T) RAID-1      64K DEGRADED Disabled DATA
"""
        )

        self.assertEqual(len(volumes), 2)
        self.assertEqual(volumes[0]["id"], "mfid0")
        self.assertEqual(volumes[0]["state"], "OPTIMAL")
        self.assertEqual(volumes[1]["state"], "DEGRADED")
        self.assertEqual(volumes[1]["name"], "DATA")

    def test_03a_should_parse_realistic_drive_list_variants(self) -> None:
        """Parse realistic `show drives` variants from different FreeBSD hosts."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_drives_real")
        context.config = {
            "at_channel": ["1:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)

        drives_mfi = runtime._MfiutilRuntime__parse_drives(
            """
mfi0 Physical Drives:
 0 ( 3726G) ONLINE <ST4000NM0033-9ZM GA0A serial=Z1Z550J2> SATA E1:S0
12 (  137G) ONLINE <FUJITSU MBE2147RC E904 serial=D314PBB00611> SAS E1:S12
"""
        )
        drives_dev = runtime._MfiutilRuntime__parse_drives(
            """
/dev/mfi0 Physical Drives:
14 (  137G) ONLINE <FUJITSU MBB2147RC D407 serial=BS03P8403LE6> SAS E1:S7
22 (  137G) ONLINE <FUJITSU MBB2147RC D407 serial=BS03P8503LUL> SAS E1:S5
"""
        )

        self.assertEqual(len(drives_mfi), 2)
        self.assertEqual(drives_mfi[0]["slot"], "E1:S0")
        self.assertEqual(drives_mfi[1]["id"], "12")
        self.assertEqual(len(drives_dev), 2)
        self.assertEqual(drives_dev[0]["slot"], "E1:S7")
        self.assertEqual(drives_dev[1]["status"], "ONLINE")

    def test_03b_should_parse_battery_status_from_realistic_output(self) -> None:
        """Parse the important battery fields from realistic command output."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_battery")
        context.config = {
            "at_channel": ["1:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)

        battery_info = runtime._MfiutilRuntime__parse_battery(
            """
mfi0: Battery State:
     Manufacture Date: 7/18/2011
        Serial Number: 0
         Manufacturer:
                Model:
            Chemistry:
      Design Capacity: 90 mAh
 Full Charge Capacity: 515 mAh
     Current Capacity: 439 mAh
        Charge Cycles: 76
       Current Charge: 86%
       Design Voltage: 0 mV
      Current Voltage: 3865 mV
          Temperature: 48 C
     Autolearn period: 90 days
      Next learn time: Tue May  5 22:51:06 2026
 Learn delay interval: 0 hours
       Autolearn mode: enabled
               Status: normal
      State of Health: good
"""
        )

        self.assertEqual(
            battery_info["summary"],
            "status=normal, health=good, charge=86%, temperature=48 C, "
            "next_learn=Tue May  5 22:51:06 2026",
        )
        self.assertEqual(battery_info["state"], "ok")

    def test_03c_should_parse_adapter_config_events_and_idle_progress(self) -> None:
        """Parse realistic adapter, config, event, and idle-progress outputs."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_status_blocks")
        context.config = {
            "at_channel": ["1:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)

        adapter_summary = runtime._MfiutilRuntime__parse_adapter(
            """
mfi0 Adapter:
    Product Name: PERC H710P Mini
   Serial Number: 42O03UF
        Firmware: 21.2.0-0007
  Battery Backup: present
"""
        )
        config_summary = runtime._MfiutilRuntime__parse_config(
            """
mfi0 Configuration: 7 arrays, 2 volumes, 0 spares
    array 0 of 2 drives:
"""
        )
        events = runtime._MfiutilRuntime__parse_events(
            """
10722 (boot + 6s/BATTERY/WARN) - Battery charging was suspended due to high battery temperature
10760 (Sun Mar 22 16:20:18 CET 2026/BATTERY/WARN) - Battery charging was suspended due to high battery temperature
"""
        )
        progress = runtime._MfiutilRuntime__parse_progress(
            controller="/dev/mfi0",
            output="No activity in progress for adapter mfi0\n",
        )

        self.assertEqual(
            adapter_summary,
            "product=PERC H710P Mini, firmware=21.2.0-0007, battery_backup=present",
        )
        self.assertEqual(config_summary, "7 arrays, 2 volumes, 0 spares")
        self.assertEqual(events[0][0], 10722)
        self.assertIn("BATTERY/WARN", events[0][1])
        self.assertEqual(progress, {})

    def test_03ca_should_parse_absent_battery_as_valid_status(self) -> None:
        """Parse `No battery present` as a valid diagnostic battery state."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_no_battery")
        context.config = {
            "at_channel": ["1:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)

        battery_info = runtime._MfiutilRuntime__parse_battery(
            "/dev/mfi0: No battery present\n"
        )
        adapter_summary = runtime._MfiutilRuntime__parse_adapter(
            """
/dev/mfi0 Adapter:
    Product Name: PERC H310 Mini
        Firmware: 20.13.1-0002
  Battery Backup: not present
"""
        )

        self.assertEqual(battery_info["summary"], "battery=not present")
        self.assertEqual(battery_info["state"], "not_present")
        self.assertEqual(
            adapter_summary,
            "product=PERC H310 Mini, firmware=20.13.1-0002, battery_backup=not present",
        )

    def test_03d_should_parse_scsi6_and_dev_path_status_variants(self) -> None:
        """Parse `SCSI-6` drives and `/dev/mfi0` status-block variants."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_srv02")
        context.config = {
            "at_channel": ["1:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)

        drives = runtime._MfiutilRuntime__parse_drives(
            """
/dev/mfi0 Physical Drives:
 0 (  559G) ONLINE <HITACHI HUS156060VLS600 A760 serial=2AX7NDVN> SCSI-6 E1:S0
 1 (  559G) ONLINE <HITACHI HUS156060VLS600 A760 serial=2AXL396N> SCSI-6 E1:S1
 4 ( 3726G) ONLINE <TOSHIBA MG03ACA4 FL1D serial=X4P5K0ZBF> SATA E1:S4
 5 ( 3726G) ONLINE <TOSHIBA MG03ACA4 FL1D serial=X4PHK4CUF> SATA E1:S5
"""
        )
        events = runtime._MfiutilRuntime__parse_events(
            """
 4667 (boot + 19s/DRIVE/WARN) - PD 00(e0x20/s0) is not a certified drive
 4670 (boot + 19s/DRIVE/WARN) - PD 01(e0x20/s1) is not a certified drive
"""
        )
        battery_info = runtime._MfiutilRuntime__parse_battery(
            """
/dev/mfi0: Battery State:
     Manufacture Date: 0/0/0
       Current Charge: 99%
          Temperature: 31 C
      Next learn time: Sat May 23 17:31:08 2026
               Status: normal
      State of Health: good
"""
        )
        adapter_summary = runtime._MfiutilRuntime__parse_adapter(
            """
/dev/mfi0 Adapter:
    Product Name: PERC H710P Mini
        Firmware: 21.3.5-0002
  Battery Backup: present
"""
        )
        config_summary = runtime._MfiutilRuntime__parse_config(
            """
/dev/mfi0 Configuration: 2 arrays, 2 volumes, 0 spares
    array 0 of 2 drives:
"""
        )
        progress = runtime._MfiutilRuntime__parse_progress(
            controller="/dev/mfi0",
            output="No activity in progress for adapter /dev/mfi0\n",
        )

        self.assertEqual(len(drives), 4)
        self.assertEqual(drives[0]["slot"], "E1:S0")
        self.assertEqual(drives[0]["status"], "ONLINE")
        self.assertEqual(events[0][0], 4667)
        self.assertIn("not a certified drive", events[1][1])
        self.assertEqual(
            battery_info["summary"],
            "status=normal, health=good, charge=99%, temperature=31 C, "
            "next_learn=Sat May 23 17:31:08 2026",
        )
        self.assertEqual(battery_info["state"], "ok")
        self.assertEqual(
            adapter_summary,
            "product=PERC H710P Mini, firmware=21.3.5-0002, battery_backup=present",
        )
        self.assertEqual(config_summary, "2 arrays, 2 volumes, 0 spares")
        self.assertEqual(progress, {})

    def test_04_should_log_only_new_events_after_baseline(self) -> None:
        """Log only events that appear after the first observed sequence cursor."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_events")
        logger = _RecordingLogger()
        context.logger = logger  # type: ignore[assignment]
        context.config = {
            "at_channel": ["1:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)

        runtime._MfiutilRuntime__log_new_events(
            controller="/dev/mfi0",
            events=[(10, "old event"), (11, "older event")],
        )
        runtime._MfiutilRuntime__log_new_events(
            controller="/dev/mfi0",
            events=[(11, "older event"), (12, "new event")],
        )

        self.assertEqual(len(logger.info_messages), 1)
        self.assertIn("new event #12", logger.info_messages[0])

    def test_04a_should_reduce_event_limit_until_history_query_succeeds(self) -> None:
        """Adaptively lower `event_count` and cache the first working limit."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_event_limit")
        context.dispatcher.publish = MagicMock()
        logger = _RecordingLogger()
        context.logger = logger  # type: ignore[assignment]
        context.config = {
            "at_channel": ["6:0;*;*;*;*"],
            "event_count": 20,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)
        runtime._tool_path = "/usr/sbin/mfiutil"
        outputs = {
            ("show", "adapter"): (
                "mfi0 Adapter:\n"
                "    Product Name: LSI MegaRAID SAS 9260-8i\n"
                "        Firmware: 12.12.0-0124\n"
                "  Battery Backup: present\n"
            ),
            ("show", "battery"): (
                "mfi0: Battery State:\n"
                "       Current Charge: 91%\n"
                "          Temperature: 32 C\n"
                "      Next learn time: Tue Apr 14 02:58:11 2026\n"
                "               Status: normal\n"
                "      State of Health: good\n"
            ),
            ("show", "config"): "mfi0 Configuration: 4 arrays, 2 volumes, 0 spares\n",
            ("show", "volumes"): (
                "/dev/mfi0 Volumes:\n"
                "  Id     Size    Level   Stripe  State   Cache   Name\n"
                " mfid0 (136G) RAID-1 64K OPTIMAL Writes\n"
            ),
            ("-e", "show", "drives"): "20 E1:S0 ONLINE healthy drive\n",
            ("show", "events", "-c", "info", "-n", "10"): (
                "43865 (Sat Mar 21 21:27:06 CET 2026/CTRL/info) - Patrol Read started\n"
            ),
            ("-e", "show", "progress"): "No activity in progress for adapter /dev/mfi0\n",
            ("locate", "E1:S0", "off"): "",
        }

        def _run(controller: str, args: List[str]) -> str:
            if tuple(args) in (
                ("show", "events", "-c", "info", "-n", "20"),
                ("show", "events", "-c", "info", "-n", "15"),
            ):
                raise RuntimeError(
                    "mfiutil command failed for controller '/dev/mfi0': "
                    "mfiutil: Event count is too high"
                )
            return outputs[tuple(args)]

        with patch.object(
            runtime,
            "_MfiutilRuntime__run_mfiutil",
            side_effect=_run,
        ):
            result = runtime._MfiutilRuntime__diagnose_controller(
                controller="/dev/mfi0",
                due_channels=[6],
            )

        self.assertFalse(result)
        self.assertFalse(context.dispatcher.publish.called)
        self.assertEqual(
            MfiutilRuntime._controller_event_limit_cache[
                "mfiutil_event_limit:/dev/mfi0"
            ],
            10,
        )
        self.assertTrue(
            any("retrying with 10" in item for item in logger.warning_messages)
        )

    def test_04b_should_continue_without_event_history_when_all_limits_fail(self) -> None:
        """Continue controller diagnostics even when event history stays unavailable."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_event_skip")
        context.dispatcher.publish = MagicMock()
        logger = _RecordingLogger()
        context.logger = logger  # type: ignore[assignment]
        context.config = {
            "at_channel": ["6:0;*;*;*;*"],
            "event_count": 3,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)
        runtime._tool_path = "/usr/sbin/mfiutil"
        outputs = {
            ("show", "adapter"): (
                "mfi0 Adapter:\n"
                "    Product Name: LSI MegaRAID SAS 9260-8i\n"
                "        Firmware: 12.12.0-0124\n"
                "  Battery Backup: present\n"
            ),
            ("show", "battery"): (
                "mfi0: Battery State:\n"
                "       Current Charge: 91%\n"
                "          Temperature: 32 C\n"
                "      Next learn time: Tue Apr 14 02:58:11 2026\n"
                "               Status: normal\n"
                "      State of Health: good\n"
            ),
            ("show", "config"): "mfi0 Configuration: 4 arrays, 2 volumes, 0 spares\n",
            ("show", "volumes"): (
                "/dev/mfi0 Volumes:\n"
                "  Id     Size    Level   Stripe  State   Cache   Name\n"
                " mfid0 (136G) RAID-1 64K OPTIMAL Writes\n"
            ),
            ("-e", "show", "drives"): "20 E1:S0 ONLINE healthy drive\n",
            ("-e", "show", "progress"): "No activity in progress for adapter /dev/mfi0\n",
            ("locate", "E1:S0", "off"): "",
        }

        def _run(controller: str, args: List[str]) -> str:
            if tuple(args[:4]) == ("show", "events", "-c", "info"):
                raise RuntimeError(
                    "mfiutil command failed for controller '/dev/mfi0': "
                    "mfiutil: Event count is too high"
                )
            return outputs[tuple(args)]

        with patch.object(
            runtime,
            "_MfiutilRuntime__run_mfiutil",
            side_effect=_run,
        ):
            result = runtime._MfiutilRuntime__diagnose_controller(
                controller="/dev/mfi0",
                due_channels=[6],
            )

        self.assertFalse(result)
        self.assertFalse(context.dispatcher.publish.called)
        self.assertTrue(
            any("event history query skipped" in item for item in logger.warning_messages)
        )
        self.assertTrue(
            any("Controller '/dev/mfi0' summary:" in item for item in logger.info_messages)
        )

    def test_05_should_locate_failed_drive_and_publish_alert(self) -> None:
        """Emit a critical alert and enable locate on a newly failed drive."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_failed")
        context.dispatcher.publish = MagicMock()
        logger = _RecordingLogger()
        context.logger = logger  # type: ignore[assignment]
        context.config = {
            "at_channel": ["7:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)
        runtime._tool_path = "/usr/sbin/mfiutil"
        outputs = {
            ("show", "adapter"): (
                "mfi0 Adapter:\n"
                "    Product Name: PERC H710P Mini\n"
                "        Firmware: 21.2.0-0007\n"
                "  Battery Backup: present\n"
            ),
            ("show", "battery"): "battery state: optimal\n",
            ("show", "config"): "mfi0 Configuration: 1 arrays, 1 volumes, 0 spares\n",
            ("show", "volumes"): (
                "/dev/mfi0 Volumes:\n"
                "  Id     Size    Level   Stripe  State   Cache   Name\n"
                " mfid0 (3726G) RAID-1 64K OPTIMAL Disabled DATA\n"
            ),
            ("-e", "show", "drives"): "0 E1:S2 FAILED drive failed\n",
            ("show", "events", "-c", "info", "-n", "10"): "1 startup event\n",
            ("-e", "show", "progress"): "",
            ("locate", "E1:S2", "on"): "",
            ("locate", "E1:S2", "off"): "",
        }

        with patch.object(
            runtime,
            "_MfiutilRuntime__run_mfiutil",
            side_effect=lambda controller, args: outputs[tuple(args)],
        ):
            result = runtime._MfiutilRuntime__diagnose_controller(
                controller="/dev/mfi0",
                due_channels=[7],
            )

        self.assertTrue(result)
        self.assertTrue(context.dispatcher.publish.called)
        self.assertTrue(
            MfiutilRuntime._locate_flags["mfiutil_failed:/dev/mfi0:E1:S2"]
        )
        self.assertTrue(
            any("product=PERC H710P Mini" in item for item in logger.info_messages)
        )

    def test_06_should_force_locate_off_for_online_drive_on_first_seen_pass(self) -> None:
        """Force `locate off` for an `ONLINE` drive on the first seen pass."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_online")
        context.dispatcher.publish = MagicMock()
        logger = _RecordingLogger()
        context.logger = logger  # type: ignore[assignment]
        context.config = {
            "at_channel": ["8:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)
        runtime._tool_path = "/usr/sbin/mfiutil"
        outputs = {
            ("show", "adapter"): (
                "mfi0 Adapter:\n"
                "    Product Name: PERC H710P Mini\n"
                "        Firmware: 21.2.0-0007\n"
                "  Battery Backup: present\n"
            ),
            ("show", "battery"): "battery state: optimal\n",
            ("show", "config"): "mfi0 Configuration: 1 arrays, 1 volumes, 0 spares\n",
            ("show", "volumes"): (
                "/dev/mfi0 Volumes:\n"
                "  Id     Size    Level   Stripe  State   Cache   Name\n"
                " mfid0 (3726G) RAID-1 64K OPTIMAL Disabled DATA\n"
            ),
            ("-e", "show", "drives"): "4 E1:S4 ONLINE replacement ready\n",
            ("show", "events", "-c", "info", "-n", "10"): "2 startup event\n",
            ("-e", "show", "progress"): "",
            ("locate", "E1:S4", "off"): "",
        }

        with patch.object(
            runtime,
            "_MfiutilRuntime__run_mfiutil",
            side_effect=lambda controller, args: outputs[tuple(args)],
        ):
            runtime._MfiutilRuntime__diagnose_controller(
                controller="/dev/mfi0",
                due_channels=[8],
            )

        self.assertFalse(
            MfiutilRuntime._locate_flags["mfiutil_online:/dev/mfi0:E1:S4"]
        )
        self.assertFalse(context.dispatcher.publish.called)

    def test_07_should_force_locate_on_for_non_online_drive_after_restart(self) -> None:
        """Force `locate on` for a non-`ONLINE` drive with empty locate cache."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_restart")
        context.dispatcher.publish = MagicMock()
        logger = _RecordingLogger()
        context.logger = logger  # type: ignore[assignment]
        context.config = {
            "at_channel": ["9:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)
        runtime._tool_path = "/usr/sbin/mfiutil"
        outputs = {
            ("show", "adapter"): (
                "mfi0 Adapter:\n"
                "    Product Name: PERC H710P Mini\n"
                "        Firmware: 21.2.0-0007\n"
                "  Battery Backup: present\n"
            ),
            ("show", "battery"): "battery state: optimal\n",
            ("show", "config"): "mfi0 Configuration: 1 arrays, 1 volumes, 0 spares\n",
            ("show", "volumes"): (
                "/dev/mfi0 Volumes:\n"
                "  Id     Size    Level   Stripe  State   Cache   Name\n"
                " mfid0 (3726G) RAID-1 64K OPTIMAL Disabled DATA\n"
            ),
            ("-e", "show", "drives"): "4 E1:S4 REBUILD replacement rebuilding\n",
            ("show", "events", "-c", "info", "-n", "10"): "2 rebuild event\n",
            ("-e", "show", "progress"): "E1:S4 rebuild is 12% complete\n",
            ("locate", "E1:S4", "on"): "",
        }

        with patch.object(
            runtime,
            "_MfiutilRuntime__run_mfiutil",
            side_effect=lambda controller, args: outputs[tuple(args)],
        ):
            runtime._MfiutilRuntime__diagnose_controller(
                controller="/dev/mfi0",
                due_channels=[9],
            )

        self.assertTrue(context.dispatcher.publish.called)
        self.assertTrue(
            MfiutilRuntime._locate_flags["mfiutil_restart:/dev/mfi0:E1:S4"]
        )

    def test_08_should_emit_alert_for_degraded_volume(self) -> None:
        """Emit a critical alert when `show volumes` reports non-OPTIMAL state."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_volume_alert")
        context.dispatcher.publish = MagicMock()
        logger = _RecordingLogger()
        context.logger = logger  # type: ignore[assignment]
        context.config = {
            "at_channel": ["10:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)
        runtime._tool_path = "/usr/sbin/mfiutil"
        outputs = {
            ("show", "adapter"): (
                "mfi0 Adapter:\n"
                "    Product Name: PERC H710P Mini\n"
                "        Firmware: 21.3.5-0002\n"
                "  Battery Backup: present\n"
            ),
            ("show", "battery"): "battery state: optimal\n",
            ("show", "config"): "mfi0 Configuration: 2 arrays, 2 volumes, 0 spares\n",
            ("show", "volumes"): (
                "/dev/mfi0 Volumes:\n"
                "  Id     Size    Level   Stripe  State   Cache   Name\n"
                " mfid0 (   68G) RAID-1      64K OPTIMAL Disabled\n"
                " mfid1 (   18T) RAID-1      64K DEGRADED Disabled DATA\n"
            ),
            ("-e", "show", "drives"): "4 E1:S4 ONLINE healthy drive\n",
            ("show", "events", "-c", "info", "-n", "10"): "1 startup event\n",
            ("-e", "show", "progress"): "",
            ("locate", "E1:S4", "off"): "",
        }

        with patch.object(
            runtime,
            "_MfiutilRuntime__run_mfiutil",
            side_effect=lambda controller, args: outputs[tuple(args)],
        ):
            result = runtime._MfiutilRuntime__diagnose_controller(
                controller="/dev/mfi0",
                due_channels=[10],
            )

        self.assertTrue(result)
        self.assertTrue(context.dispatcher.publish.called)
        self.assertTrue(
            any("Volume: mfid1" in item for item in logger.warning_messages)
        )

    def test_09_should_emit_alert_for_failed_battery(self) -> None:
        """Emit a critical alert for current failed battery health."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_battery_alert")
        context.dispatcher.publish = MagicMock()
        logger = _RecordingLogger()
        context.logger = logger  # type: ignore[assignment]
        context.config = {
            "at_channel": ["11:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)
        runtime._tool_path = "/usr/sbin/mfiutil"
        outputs = {
            ("show", "adapter"): (
                "mfi0 Adapter:\n"
                "    Product Name: PERC 6/i Integrated\n"
                "        Firmware: 6.3.3.0002\n"
                "  Battery Backup: present\n"
            ),
            ("show", "battery"): (
                "mfi0: Battery State:\n"
                "       Current Charge: 91%\n"
                "          Temperature: 21 C\n"
                "      Next learn time: Mon Apr 20 06:53:35 2026\n"
                "               Status: normal\n"
                "      State of Health: bad\n"
            ),
            ("show", "config"): "mfi0 Configuration: 4 arrays, 3 volumes, 0 spares\n",
            ("show", "volumes"): (
                "mfi0 Volumes:\n"
                "  Id     Size    Level   Stripe  State   Cache   Name\n"
                " mfid0 (136G) RAID-1 64K OPTIMAL Disabled system\n"
            ),
            ("-e", "show", "drives"): "0 E1:S0 ONLINE healthy drive\n",
            (
                "show",
                "events",
                "-c",
                "info",
                "-n",
                "10",
            ): (
                "54181 (Tue Oct 24 12:24:45 CEST 2023/BATTERY/WARN) - "
                "BBU disabled; changing WB virtual disks to WT, "
                "Forced WB VDs are not affected\n"
            ),
            ("-e", "show", "progress"): "",
            ("locate", "E1:S0", "off"): "",
        }

        with patch.object(
            runtime,
            "_MfiutilRuntime__run_mfiutil",
            side_effect=lambda controller, args: outputs[tuple(args)],
        ):
            result = runtime._MfiutilRuntime__diagnose_controller(
                controller="/dev/mfi0",
                due_channels=[11],
            )

        self.assertTrue(result)
        self.assertTrue(context.dispatcher.publish.called)
        self.assertTrue(
            any("Battery State: failed" in item for item in logger.warning_messages)
        )

    def test_10_should_log_battery_temperature_warnings_without_alert(self) -> None:
        """Keep repeated battery-temperature warnings in logs only."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_battery_warn")
        context.dispatcher.publish = MagicMock()
        logger = _RecordingLogger()
        context.logger = logger  # type: ignore[assignment]
        context.config = {
            "at_channel": ["12:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)
        runtime._tool_path = "/usr/sbin/mfiutil"
        MfiutilRuntime._controller_event_cursor[
            "mfiutil_battery_warn:/dev/mfi0"
        ] = 56384
        outputs = {
            ("show", "adapter"): (
                "mfi0 Adapter:\n"
                "    Product Name: PERC H710P Mini\n"
                "        Firmware: 21.2.0-0007\n"
                "  Battery Backup: present\n"
            ),
            ("show", "battery"): (
                "mfi0: Battery State:\n"
                "       Current Charge: 84%\n"
                "          Temperature: 50 C\n"
                "      Next learn time: Wed Apr 29 06:28:56 2026\n"
                "               Status: normal\n"
                "      State of Health: good\n"
            ),
            ("show", "config"): "mfi0 Configuration: 7 arrays, 2 volumes, 0 spares\n",
            ("show", "volumes"): (
                "mfi0 Volumes:\n"
                "  Id     Size    Level   Stripe  State   Cache   Name\n"
                " mfid0 (136G) RAID-1 64K OPTIMAL Disabled SYSTEM\n"
            ),
            ("-e", "show", "drives"): "0 E1:S0 ONLINE healthy drive\n",
            (
                "show",
                "events",
                "-c",
                "info",
                "-n",
                "10",
            ): (
                "65192 (Tue Feb  3 16:40:16 CET 2026/BATTERY/WARN) - "
                "Battery charging was suspended due to high battery temperature\n"
            ),
            ("-e", "show", "progress"): "",
            ("locate", "E1:S0", "off"): "",
        }

        with patch.object(
            runtime,
            "_MfiutilRuntime__run_mfiutil",
            side_effect=lambda controller, args: outputs[tuple(args)],
        ):
            result = runtime._MfiutilRuntime__diagnose_controller(
                controller="/dev/mfi0",
                due_channels=[12],
            )

        self.assertFalse(result)
        self.assertFalse(context.dispatcher.publish.called)
        self.assertTrue(
            any("battery state: status=normal, health=good" in item.lower() for item in logger.info_messages)
        )
        self.assertTrue(
            any("BATTERY/WARN" in item for item in logger.info_messages)
        )

    def test_11_should_not_alert_for_historical_critical_events_when_current_state_is_healthy(
        self,
    ) -> None:
        """Keep historical critical events in logs when current state is healthy."""
        from plugins.mfiutil.plugin.runtime import MfiutilRuntime

        context = self.__build_context("mfiutil_historical_events")
        context.dispatcher.publish = MagicMock()
        logger = _RecordingLogger()
        context.logger = logger  # type: ignore[assignment]
        context.config = {
            "at_channel": ["13:0;*;*;*;*"],
            "event_count": 10,
            "sleep_period": 30.0,
            "tool_path": "/usr/sbin/mfiutil",
        }
        runtime = MfiutilRuntime(context)
        runtime._tool_path = "/usr/sbin/mfiutil"
        MfiutilRuntime._controller_event_cursor[
            "mfiutil_historical_events:/dev/mfi0"
        ] = 134257
        outputs = {
            ("show", "adapter"): (
                "mfi0 Adapter:\n"
                "    Product Name: PERC H710P Mini\n"
                "        Firmware: 21.3.0-0009\n"
                "  Battery Backup: present\n"
            ),
            ("show", "battery"): (
                "mfi0: Battery State:\n"
                "       Current Charge: 95%\n"
                "          Temperature: 35 C\n"
                "      Next learn time: Tue May 19 07:25:12 2026\n"
                "               Status: normal\n"
                "      State of Health: good\n"
            ),
            ("show", "config"): "mfi0 Configuration: 6 arrays, 3 volumes, 0 spares\n",
            ("show", "volumes"): (
                "mfi0 Volumes:\n"
                "  Id     Size    Level   Stripe  State   Cache   Name\n"
                " mfid0 (68G) RAID-1 64K OPTIMAL Disabled SYSTEM\n"
                " mfid1 (3726G) RAID-1 64K OPTIMAL Disabled DATA2\n"
                " mfid2 (3724G) RAID-10 64K OPTIMAL Disabled DATA\n"
            ),
            ("-e", "show", "drives"): "10 E1:S10 ONLINE healthy drive\n",
            (
                "show",
                "events",
                "-c",
                "info",
                "-n",
                "10",
            ): (
                "134258 (Sat Oct 11 04:00:40 CEST 2025/DRIVE/WARN) - "
                "PD 0a(e0x20/s10) Path 500056b37789abe5  reset (Type 03)\n"
                "134260 (Sat Oct 11 04:00:44 CEST 2025/DRIVE/FATAL) - "
                "Patrol Read found an uncorrectable medium error on PD 0a(e0x20/s10) at 6a720\n"
                "134265 (Sat Oct 11 04:00:44 CEST 2025/VOLUME/CRIT) - "
                "VOL mfid1 event: VD 02/1 is now DEGRADED\n"
                "134279 (Sat Oct 11 04:02:31 CEST 2025/DRIVE/CRIT) - "
                "Rebuild failed on PD 0a(e0x20/s10) due to target drive error\n"
                "134359 (Sat Oct 11 04:52:33 CEST 2025/DRIVE/FATAL) - "
                "Unable to access device PD 0a(e0x20/s10)\n"
            ),
            ("-e", "show", "progress"): "",
            ("locate", "E1:S10", "off"): "",
        }

        with patch.object(
            runtime,
            "_MfiutilRuntime__run_mfiutil",
            side_effect=lambda controller, args: outputs[tuple(args)],
        ):
            result = runtime._MfiutilRuntime__diagnose_controller(
                controller="/dev/mfi0",
                due_channels=[13],
            )

        self.assertFalse(result)
        self.assertFalse(context.dispatcher.publish.called)
        self.assertTrue(any("DRIVE/FATAL" in item for item in logger.info_messages))


# #[EOF]#######################################################################
