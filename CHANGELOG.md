# Changelog

All notable changes to this plugin repository are documented in this file.

## [0.3.7] - 2026-03-27

### Changed
- Populated `Message.diagnostic_source` in `plugins/mfiutil/plugin/runtime.py`
  so dispatcher warnings for unregistered channels identify the producing
  runtime class.
- Updated `plugins/mfiutil/README.md` to document the dispatcher diagnostic
  source attached to emitted notifications.

### Versioning
- Bumped local plugin version to `0.3.7` in `plugins/mfiutil/plugin/__init__.py`.

## [0.3.6] - 2026-03-26

### Changed
- Updated `plugins/mfiutil/plugin/runtime.py` so every plugin start performs an
  immediate diagnostic pass before waiting for the next `at_channel` window.
- Kept minute-level schedule deduplication so a startup scan that lands inside
  an already matching `at_channel` minute does not trigger a duplicate pass in
  the same slot.
- Added regression coverage in `plugins/mfiutil/tests/test_runtime.py` for the
  immediate startup scan and the no-duplicate overlap case.
- Updated `plugins/mfiutil/README.md` to document immediate startup diagnostics
  and the resulting behavior after daemon restart or `SIGHUP` reload.

### Versioning
- Bumped local plugin version to `0.3.6` in `plugins/mfiutil/plugin/__init__.py`.

## [0.3.5] - 2026-03-26

### Changed
- Added per-minute schedule deduplication in
  `plugins/mfiutil/plugin/runtime.py` so one matching `at_channel` slot triggers
  at most one diagnostic pass even when the polling interval is shorter than
  sixty seconds.
- Changed `sleep_period` in `plugins/mfiutil/load.py` to an optional setting
  with a runtime default of `5.0` seconds.
- Added regression coverage in `plugins/mfiutil/tests/test_runtime.py` for
  schedule-slot deduplication and the default sleep-period fallback.
- Updated `plugins/mfiutil/README.md` to document the deduplicated schedule
  behavior and the optional `sleep_period`.

### Versioning
- Bumped local plugin version to `0.3.5` in `plugins/mfiutil/plugin/__init__.py`.

## [0.3.4] - 2026-03-25

### Changed
- Switched `plugins/mfiutil/plugin/runtime.py` from the newer `-D <device>`
  selector to the cross-version `-u <unit>` syntax while keeping controller
  discovery based on `/dev/mfi*` and `/dev/mrsas*` device nodes.
- Added regression coverage in `plugins/mfiutil/tests/test_runtime.py` for
  multi-controller device detection and `-u <unit>` command construction.
- Updated `plugins/mfiutil/README.md` to document the cross-version command
  strategy.

### Versioning
- Bumped local plugin version to `0.3.4` in `plugins/mfiutil/plugin/__init__.py`.

## [0.3.3] - 2026-03-25

### Changed
- Hardened `plugins/mfiutil/plugin/runtime.py` so that `show events` uses an
  adaptive fallback when a controller rejects the configured `event_count`
  value with `Event count is too high`.
- Lowered the default `event_count` in `plugins/mfiutil/load.py` from `50` to
  `10`, matching observed controller compatibility while keeping the adaptive
  fallback path for stricter firmware variants.
- Cached the first working event-history limit per controller instance to avoid
  repeating oversized queries on later diagnostic passes.
- Changed event-history failures to warning-only behavior so adapter, battery,
  volume, drive, and progress diagnostics still complete when historical event
  reads remain unavailable.
- Added regression coverage in `plugins/mfiutil/tests/test_runtime.py` for
  adaptive event-limit fallback and continuation of diagnostics when event
  history must be skipped.
- Updated `plugins/mfiutil/README.md` to document adaptive event-count fallback
  and non-blocking event-history failures.

### Versioning
- Bumped local plugin version to `0.3.3` in `plugins/mfiutil/plugin/__init__.py`.

## [0.3.2] - 2026-03-25

### Changed
- Refined `plugins/mfiutil/plugin/runtime.py` so that current alerting is based
  only on current controller state from `show drives`, `show volumes`,
  `show config`, and `show battery`, while `show events` remains historical log
  context only.
- Added regression coverage in `plugins/mfiutil/tests/test_runtime.py` for
  historical critical events that no longer trigger alerts when current drive,
  volume, and battery state is healthy.
- Updated `plugins/mfiutil/README.md` to document that event-log entries are
  diagnostic history rather than the authoritative current state.

### Versioning
- Bumped local plugin version to `0.3.2` in `plugins/mfiutil/plugin/__init__.py`.

## [0.3.1] - 2026-03-25

### Changed
- Added regression coverage in `plugins/mfiutil/tests/test_runtime.py` to keep
  non-actionable `BATTERY/WARN` temperature events in logs only.
- Updated `plugins/mfiutil/README.md` to clarify that battery-temperature
  warnings do not trigger channel alerts by themselves.

### Versioning
- Bumped local plugin version to `0.3.1` in `plugins/mfiutil/plugin/__init__.py`.

## [0.3.0] - 2026-03-25

### Added
- Added battery-state alerting in `plugins/mfiutil/plugin/runtime.py` for
  controllers reporting failed battery health or fatal battery events.
- Added regression coverage in `plugins/mfiutil/tests/test_runtime.py` for
  failed battery health and `BATTERY/FATAL` event handling.

### Changed
- Changed battery parsing in `plugins/mfiutil/plugin/runtime.py` to return both
  a normalized state and a human-readable summary for diagnostics.
- Updated `plugins/mfiutil/README.md` to document battery alert behavior.

### Versioning
- Bumped local plugin version to `0.3.0` in `plugins/mfiutil/plugin/__init__.py`.

## [0.2.1] - 2026-03-25

### Changed
- Hardened `plugins/mfiutil/plugin/runtime.py` battery parsing to treat
  `No battery present` as a valid FreeBSD controller status instead of an empty
  summary.
- Added regression coverage in `plugins/mfiutil/tests/test_runtime.py` for
  controllers without battery backup.
- Updated `plugins/mfiutil/README.md` to document the no-battery variant.

### Versioning
- Bumped local plugin version to `0.2.1` in `plugins/mfiutil/plugin/__init__.py`.

## [0.2.0] - 2026-03-25

### Added
- Added `show volumes` parsing in `plugins/mfiutil/plugin/runtime.py` to detect
  controller volumes whose state is not `OPTIMAL`.
- Added channel alerts for non-`OPTIMAL` volume states, especially
  `DEGRADED`, with per-volume state caching to avoid repeated alerts for the
  same unchanged state.
- Added regression coverage in `plugins/mfiutil/tests/test_runtime.py` for
  volume-table parsing and degraded-volume alerting.

### Changed
- Updated `plugins/mfiutil/README.md` to document volume-state diagnostics and
  alerting.

### Versioning
- Bumped local plugin version to `0.2.0` in `plugins/mfiutil/plugin/__init__.py`.

## [0.1.4] - 2026-03-25

### Changed
- Simplified `plugins/mfiutil/plugin/runtime.py` locate handling to reconcile
  controller LEDs from observed drive status on every diagnostic pass:
  `ONLINE -> locate off`, any other status -> `locate on`.
- Updated `plugins/mfiutil/tests/test_runtime.py` to cover forced `locate off`
  on first-seen `ONLINE` drives and forced `locate on` after restart for
  non-`ONLINE` drives.
- Updated `plugins/mfiutil/README.md` to document the lack of controller-side
  `locate` readback and the resulting reconciliation strategy.

### Versioning
- Bumped local plugin version to `0.1.4` in `plugins/mfiutil/plugin/__init__.py`.

## [0.1.3] - 2026-03-25

### Changed
- Extended `plugins/mfiutil/tests/test_runtime.py` with additional regression
  coverage for FreeBSD outputs using `SCSI-6` drives, event lines with leading
  whitespace, `/dev/mfi0` battery and adapter headers, and idle progress output
  reported as `adapter /dev/mfi0`.
- Updated `plugins/mfiutil/README.md` to document support for these realistic
  `mfiutil` output variants.

### Versioning
- Bumped local plugin version to `0.1.3` in `plugins/mfiutil/plugin/__init__.py`.

## [0.1.2] - 2026-03-25

### Changed
- Extended `plugins/mfiutil/plugin/runtime.py` to parse and log controller
  adapter summaries and `show config` summaries during each diagnostic pass.
- Hardened regression coverage in `plugins/mfiutil/tests/test_runtime.py` with
  realistic FreeBSD samples for `show drives`, `show adapter`, `show config`,
  `show events`, and idle `show progress` output.
- Updated `plugins/mfiutil/README.md` to document adapter/config log behavior.

### Versioning
- Bumped local plugin version to `0.1.2` in `plugins/mfiutil/plugin/__init__.py`.

## [0.1.1] - 2026-03-25

### Changed
- Improved battery-status parsing in `plugins/mfiutil/plugin/runtime.py` to log
  structured FreeBSD `mfiutil show battery` fields.
- Added regression coverage for realistic battery output in
  `plugins/mfiutil/tests/test_runtime.py`.

### Versioning
- Bumped local plugin version to `0.1.1` in `plugins/mfiutil/plugin/__init__.py`.

## [0.1.0] - 2026-03-25

### Added
- Added FreeBSD-only scheduled `mfiutil` diagnostics in `plugins/mfiutil/plugin/runtime.py`.
- Added controller auto-discovery, battery logging, event logging, failed-drive locate handling, and rebuild-progress notifications.
- Added plugin-local regression coverage in `plugins/mfiutil/tests/test_runtime.py`.
- Documented FreeBSD scope, configuration, and alert behavior in `plugins/mfiutil/README.md`.

### Changed
- Replaced template worker configuration with mfiutil-specific fields in `plugins/mfiutil/load.py`.
- Replaced template worker keys with mfiutil-specific runtime keys in `plugins/mfiutil/plugin/config.py`.

### Versioning
- Bumped local plugin version to `0.1.0` in `plugins/mfiutil/plugin/__init__.py`.

## [0.0.1] - 2026-03-25

### Changed
- Updated module, class, and method docstrings in `plugins/mfiutil/load.py`.
- Updated package and module docstrings in `plugins/mfiutil/plugin/__init__.py`.
- Updated module and class docstrings in `plugins/mfiutil/plugin/config.py`.
- Updated module, class, and method docstrings in `plugins/mfiutil/plugin/runtime.py`.
- Updated package docstring in `plugins/mfiutil/__init__.py`.
- Updated repository description in `plugins/mfiutil/README.md`.

### Versioning
- Initialized local plugin version to `0.0.1` in `plugins/mfiutil/plugin/__init__.py`.
