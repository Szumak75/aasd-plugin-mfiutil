# -*- coding: UTF-8 -*-
"""
Mfiutil worker plugin configuration keys.

Author:  Jacek 'Szumak' Kotlarski --<szumak@virthost.pl>
Created: 2026-03-24

Purpose: Provide plugin-specific configuration keys for the mfiutil worker
plugin.
"""

from jsktoolbox.attribtool import ReadOnlyClass


class Keys(object, metaclass=ReadOnlyClass):
    """Define plugin-specific configuration keys for the mfiutil worker."""

    # #[CONSTANTS]####################################################################
    EVENT_COUNT: str = "event_count"
    TOOL_PATH: str = "tool_path"


# #[EOF]#######################################################################
