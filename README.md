# AASd v2 Mfiutil Worker Plugin

This directory contains a standalone AASd worker plugin repository prepared
for `mfiutil`-based monitoring tasks on FreeBSD systems.

## Included Files

- `load.py` - required daemon entry point exposing `get_plugin_spec()`
- `plugin/__init__.py` - plugin package marker and local plugin version
- `plugin/config.py` - plugin-specific configuration keys
- `plugin/runtime.py` - thread-based worker runtime implementation
- `requirements.txt` - plugin-local runtime dependencies placeholder
- `CHANGELOG.md` - local plugin change history
- `tests/` - plugin-local runtime regression coverage

## Platform Scope

This plugin targets **FreeBSD** only.

It relies on the `mfiutil` utility shipped in the FreeBSD base system for
diagnosing supported `mfi(4)` and `mrsas(4)` controllers. The plugin does not
expect `mfiutil` to be installed from ports or packages.

## Current Scope

The current implementation:

- auto-discovers `mfiutil` in standard FreeBSD system locations and `PATH`,
- detects one or more supported controllers from `/dev/mfi*` and `/dev/mrsas*`,
- executes controller commands through the cross-version `mfiutil -u <unit>`
  syntax derived from the detected device node,
- parses realistic FreeBSD `mfiutil` output variants seen across controller and
  system versions, including `/dev/mfiX` headers and mixed SATA/SAS/SCSI drive
  descriptions,
- runs diagnostics according to `AT_CHANNEL`,
- logs adapter and configuration summaries for each detected controller,
- evaluates `show volumes` and emits alerts when one or more volumes are not in
  `OPTIMAL` state,
- evaluates current battery health and emits alerts only for currently failed
  battery conditions,
- emits channel notifications only for critical drive conditions and rebuild
  progress updates,
- logs battery status and newly observed controller events without channel
  notifications,
- adaptively lowers the `show events` query limit when a controller rejects the
  configured `event_count` value and remembers the first working limit per
  controller for later passes,
- actively forces `locate on` for every drive whose current status is not
  `ONLINE`,
- actively forces `locate off` for every drive whose current status is
  `ONLINE`, including the first diagnostic pass after plugin startup.

The runtime keeps cached disk state, locate state, rebuild progress, and event
sequence cursors in class-level storage for repeated diagnostic passes.

## Configuration

The plugin currently exposes the following configuration fields:

- `at_channel` - cron-like schedule driving diagnostics and channel delivery
- `sleep_period` - optional polling interval between schedule checks, default `5.0`
- `event_count` - maximum number of controller events read per low-level event
  fetch request, default `10`
- `tool_path` - optional explicit path to `mfiutil`

The runtime checks the configured schedule in a polling loop and deduplicates
execution per scheduled minute. This means a value such as
`at_channel = ['1:0;0|6|12|18;*;*;*']` is executed at most once per matching
minute even when `sleep_period` is shorter than sixty seconds.

## Notification Rules

Channel notifications are emitted only for:

- volume states other than `OPTIMAL`, especially `DEGRADED`,
- current failed battery state reported by `show battery`,
- critical drive states requiring operator attention or replacement,
- rebuild progress updates when the reported percentage changes.

Battery status is written only to plugin logs. Newly detected controller events
since plugin startup are also written only to plugin logs. Controller adapter
and configuration summaries are also written only to plugin logs. Controllers
without a battery are treated as valid hardware variants and are logged as
`battery=not present`.
Battery warnings such as suspended charging caused by high battery temperature
are also kept in logs only unless current battery health becomes bad. Event log
entries are treated as historical diagnostics only and do not define current
controller health by themselves. If `mfiutil show events` rejects the current
`event_count` with `Event count is too high`, the plugin retries with lower
limits and, if needed, skips event history while continuing the remaining
controller diagnostics.

Because `mfiutil` does not expose a read command for current `locate` state, the
plugin uses an operational simplification: every pass reconciles `locate`
against the current drive status instead of attempting controller-side state
discovery.

## Design Notes

The plugin follows the current recommended worker-plugin pattern:

- `PluginSpec` and `PluginContext` from the public runtime API
- package-relative imports inside `load.py` and `plugin/*`
- `PluginCommonKeys.AT_CHANNEL` for scheduled diagnostics and notification windows
- `NotificationScheduler` for reusable cron-like notification decisions
- `ThPluginMixin` for typed runtime-owned storage
- local private key constants based on `ReadOnlyClass`
- explicit narrowing of `Optional[...]` runtime properties
- `PluginStateSnapshot` and `PluginHealthSnapshot` fallbacks for guard paths

For broader project guidance, see:

- `docs/PluginAPI.md`
- `docs/PluginChecklist.md`
- `docs/PluginRepositoryModel.md`
