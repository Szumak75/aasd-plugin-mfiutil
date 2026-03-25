# Changelog

All notable changes to this plugin repository are documented in this file.

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
