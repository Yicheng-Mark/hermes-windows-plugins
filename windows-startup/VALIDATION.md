# Validation — hermes-windows-startup

Everything below was measured on the machine this plugin was written on
(Windows 11, unelevated user, Python 3.13), with the commands shown.

## The sources, live

- `HKLM\...\CurrentVersion\Run`: 2 values (`SecurityHealth`, `RtkAudUService`).
- `HKCU\...\CurrentVersion\Run`: 1 value — `CC Switch`, written **unquoted with a space
  in the path and a trailing space** (`C:\Users\...\Programs\CC Switch\cc-switch.exe `),
  which is exactly the shape that breaks naive first-token binary resolution; the
  longest-prefix resolver answers `cc-switch.exe`, present on disk.
- `HKLM\SOFTWARE\WOW6432Node\...\Run`: the key exists and carries 0 values on this
  64-bit install — swept, reported empty, never an error.
- User and common Startup folders exist; the user's carries only `desktop.ini` (skipped
  as folder customization, not an entry).
- `User Shell Folders\Startup` is not OneDrive-redirected here, but is read through
  Explorer's value so a redirected machine is found by construction.

## The StartupApproved verdict, live

- `CC Switch` → state byte `02`, enabled, no change timestamp.
- `SecurityHealth` → disabled: the machine's HKLM `StartupApproved\Run` record carries
  the switched-off state, and the table reports `enabled: disabled` for an entry the
  Run key still lists — the Task Manager fact, from the registry, in 1 ms.
- `EgoAutoLaunch_9896BAC20DA36D18D18466E6BF14A167` → state byte `01` with a FILETIME
  (2026-10-18T09:21:52Z), and **no matching Run value**: an orphan an uninstalled
  program left behind. Reported under `leftover_approvals` and counted in the notes;
  its `01` byte is surfaced as `unknown (state byte 1)`, not guessed into a verdict.

## Cost

- `win_startup_table({})`: 0.001 s — three Run values, six Run/RunOnce keys, two
  approval keys per hive, two folder listings, no PowerShell, no WMI.
- `win_startup_detail({"name": "cc switch"})`: 0.000 s beyond the sweep, including
  binary resolution through the space-in-path command.

## Tests

16 pass on this machine: 11 unit (fake hive tree through an injected opener, fake
folders, import behind a `winreg` blocker proving the module loads where `winreg` does
not exist) + 5 live (the facts above, as assertions).

## Admission validator

`hermes plugins validate` (via `hermes_cli.plugin_validate.validate_plugin_dir`) on the
working copy and on the pinned tarball: **15/15 PASS, zero warnings, security scan
safe** — the exact gate the catalog runs on Linux CI, satisfied locally on Windows,
with the `winreg`-less import covered by a unit test for the platform the validator
actually runs on.
