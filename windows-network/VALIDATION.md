# Validation

What was checked before this plugin was submitted, on which machine, and what the numbers
were. Everything below was run on Windows 11 (build 26300, display language Chinese),
Python 3.13, against the `hermes-agent` admission validator from the 10-19 main tree.

## Admission checks

`validate_plugin_dir` reports **15/15 checks pass, security scan safe, zero warnings** on
this directory. The plugin suite is **33 passed** (28 unit on fakes, 5 live on this
machine).

## What a person sees, on this machine

- `win_adapter_table({})` lists 3 visible adapters in **0.8 s** (plus 2 ghosts whose
  hardware is not present, hidden until `include_absent=true`): the wireless adapter up
  at 526.5 Mbps, the ethernet adapter disconnected ("no medium"), and a Hyper-V virtual
  adapter flagged virtual. `win_adapter_detail` answers in **2.6 s** (a second
  PowerShell call).
- The disconnected ethernet adapter is this machine's own live textbook case: address
  `169.254.57.204/16` with origin "WellKnown" (self-assigned), no default gateway, and a
  static DNS server left over from a network it is no longer on. The tool says all three:
  no medium, DHCP did not answer, and the configured DNS servers cannot be reached
  without a gateway.
- Cross-checked against `ipconfig` on the same machine: the wireless adapter's address
  (`192.168.0.200`) and default gateway (`192.168.0.1`) are identical in both.

## Why the cmdlets, and what the traps were

- `Get-NetAdapter`'s `Status` comes back as enum names ("Up", "Disconnected", "Not
  Present") that do **not** change with the display language, checked on a machine set
  to Chinese; the adapter's `Name` does localize ("以太网") and is carried as data, never
  parsed. The link speed is read from the raw bits-per-second property because the
  display string ("2.5 Gbps" and its translations) follows the language.
- `Get-NetIPConfiguration -InterfaceIndex N` **throws** for an adapter IP is not bound to
  (the Hyper-V host adapter here), which under `ErrorActionPreference='Stop'` kills the
  whole script -- so the detail call lists every configuration once and filters in
  PowerShell, and every property build is wrapped so one adapter cannot take the answer
  down.
- `DriverDate` arrives as a string on some adapters and a DateTime on others; the cast
  is tried, not assumed.
- An `if` expression as an object property unwraps a one-element array into a bare
  object and an empty one into `{}` (a live run answered with the one wireless address
  as a bare object); the script wraps every list in `@(...)`, and the Python side also
  normalises a bare row or `{}` back into the list it meant, with a regression test.
