# Validation

What was checked before this plugin was submitted, on which machine, and what the numbers
were. Everything below was run on Windows 11 (build 26300), Python 3.13, against the
`hermes-agent` admission validator from the 10-19 main tree.

## Admission checks

`validate_plugin_dir` reports **15/15 checks pass, security scan safe, zero warnings** on
this directory, and again on the tree extracted from the repository tarball at the pinned
commit. The plugin suite is **15 passed** (11 unit on fakes, 4 live on this machine),
on the working copy and inside the pin tarball.

## Why CIM and not the Device Manager store

- `Win32_PnPEntity` lists 235 devices in 1.7 s unelevated, with `PNPClass`,
  `ConfigManagerErrorCode`, `Manufacturer`, `Present` and the stable `DeviceID`; property
  names, enum values and ids do not change with the display language (the human-facing
  `Name`/`Manufacturer` localize — they are carried through as data, never parsed).
- `Win32_PnPSignedDriver` is the only place the driver behind a device is named with its
  version, date, signer and INF; 239 rows in 2.2 s, joined to the tree by device id.
- `Present` separates historical devices (unplugged) from live ones: the listing defaults
  to present-only, `include_absent=true` brings the history back.

## What a person sees

- `win_device_table({"broken_only": True})` on this machine finds exactly one device:
  `ROOT\LENOVO_VIRTUAL_BUS\0000`, problem code `28`, "no driver is installed for it" —
  the same device the machine's own system log has been noting as noise.
- `win_device_detail` on that device shows `driver: null` and a note saying the empty
  driver section and the code-28 problem are the same fact.
- `win_device_detail` on the wireless adapter joins the driver row: version `23.20.0.6`,
  dated 2026-01-15, signed by Microsoft Windows Hardware Compatibility Publisher.
