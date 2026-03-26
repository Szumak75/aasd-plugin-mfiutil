# -*- coding: UTF-8 -*-
"""
Mfiutil worker plugin entry point.

Author:  Jacek 'Szumak' Kotlarski --<szumak@virthost.pl>
Created: 2026-03-24

Purpose: Provide the plugin manifest for the standalone mfiutil worker plugin.
"""

from libs.plugins import PluginCommonKeys, PluginKind, PluginSpec
from libs.templates import PluginConfigField, PluginConfigSchema

from .plugin import __version__
from .plugin.config import Keys
from .plugin.runtime import MfiutilRuntime


def get_plugin_spec() -> PluginSpec:
    """Return the plugin spec for the mfiutil worker plugin.

    ### Returns:
    PluginSpec - Plugin manifest.
    """
    schema = PluginConfigSchema(
        title="Mfiutil worker plugin.",
        description=(
            "FreeBSD worker plugin that runs scheduled mfiutil diagnostics for "
            "supported MegaRAID controllers and emits alerts for critical states."
        ),
        fields=[
            PluginConfigField(
                name=PluginCommonKeys.AT_CHANNEL,
                field_type=list,
                default=["1:0;0|6|12|18;*;*;*"],
                required=True,
                description=(
                    "Cron-like notification targets used for scheduled controller "
                    "diagnostics and critical alert delivery."
                ),
            ),
            PluginConfigField(
                name=PluginCommonKeys.SLEEP_PERIOD,
                field_type=float,
                default=5.0,
                required=False,
                description=(
                    "Optional polling interval in seconds used between schedule "
                    "checks. Defaults to 5.0 seconds."
                ),
            ),
            PluginConfigField(
                name=Keys.EVENT_COUNT,
                field_type=int,
                default=10,
                required=True,
                description="Maximum number of controller events read on each diagnostic pass.",
            ),
            PluginConfigField(
                name=Keys.TOOL_PATH,
                field_type=str,
                default="",
                required=False,
                description=(
                    "Optional explicit path to mfiutil. When empty, the plugin "
                    "searches standard FreeBSD base-system locations and PATH."
                ),
                example="/usr/sbin/mfiutil",
            ),
        ],
    )
    return PluginSpec(
        api_version=1,
        config_schema=schema,
        plugin_id="mfiutil.worker",
        plugin_kind=PluginKind.WORKER,
        plugin_name="plugin_mfiutil",
        runtime_factory=MfiutilRuntime,
        description="FreeBSD worker plugin for scheduled mfiutil controller diagnostics.",
        plugin_version=__version__,
    )


# #[EOF]#######################################################################
