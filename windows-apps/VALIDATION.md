# Validation — hermes-windows-apps

Everything below was measured on the machine this plugin was written on
(Windows 11, unelevated user, Python 3.13), with the commands shown.

## The four keys, live

- `HKLM\...\Uninstall`: 52 subkeys; `HKLM\...\WOW6432Node\...\Uninstall`:
  35; `HKCU\...\Uninstall`: 15 — **102 entries swept in 0.007 s**, pure
  `winreg`, no PowerShell, no WMI, no elevation.
- The user's 32-bit view key does not exist on this install: swept, reported
  empty, never an error — the same honest-empty rule the other views follow
  when a machine lacks them.
- No subkey refused an unelevated read here; the unreadable path (security
  software writes such keys) is covered by a unit test instead.

## What a real inventory looks like through the tools

- `win_app_table({})`: 0.010 s, **51 visible rows, 73 named programs** —
  **22 hidden from Apps & Features** (`SystemComponent`: runtimes, the Edge
  WebView2 runtime among them), surfaced only with
  `include_system_components=true`, exactly as the schema promises.
- **1 program installed in more than one view** (2 raw names) — the collapse
  listed it once with its view list, the dual-install shape Apps & Features
  itself shows once.
- Sizes read true: Microsoft Edge 2129.9 MB (machine-32), WPS Office
  1357.5 MB **in the user view** — the per-user install the machine page never
  lists, found because the user's key is swept too. Install dates parse from
  both shapes in the wild (`20261101` and localized forms); publishers that
  wrote none report `null`, never a guess.
- `win_app_detail({"name": "obs"})`: the one occurrence carries version
  33.0.1 and an uninstall string that is a **quoted path with spaces**
  (`"D:\apply\obs-studio\uninstall.exe"`) — classified `setup executable`;
  the quoted-segment rule exists because this machine's real data has that
  exact shape.

## Cost

- The sweep is four key opens plus ~1700 value reads: 0.007 s. The table adds
  collapse, filtering and sort: 0.010 s total. The detail reuses the sweep:
  no measurable cost beyond it.

## Tests

19 pass on this machine: 14 unit (a fake hive tree walked through an injected
opener — hidden flags, dual-install collapse, both date shapes, uninstaller
classification including the quoted-path case, the winreg-less import behind
a blocker) + 5 live (the facts above, as assertions).

## Admission validator

`hermes plugins validate` (via `hermes_cli.plugin_validate.validate_plugin_dir`)
on the working copy and on the pinned tarball: **15/15 PASS, zero warnings,
security scan safe** — the exact gate the catalog runs on Linux CI, satisfied
locally on Windows, with the `winreg`-less import covered by a unit test for
the platform the validator actually runs on.

## Disclosure

The plugin reads the four Uninstall registry keys (machine and user hives) and
reports what publishers wrote there: names, versions, publishers, sizes,
install dates, install locations, help links, and the uninstall commands
themselves, classified but never executed. Nothing is uninstalled, modified,
written or run; no network access; no elevation is requested or needed to
read these keys.
