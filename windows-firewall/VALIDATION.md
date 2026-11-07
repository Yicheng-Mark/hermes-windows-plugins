# Validation — hermes-windows-firewall

Everything below was measured on the machine this plugin was written on
(Windows 11 build 26100, unelevated user, Python 3.13), with the commands
shown.

## The rule store, live

- `HKLM\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\
  FirewallPolicy\FirewallRules`: **795 rules, every one `v2.33`**, swept as
  one key open plus 795 value enumerations in **0.071 s** -- pure `winreg`,
  no PowerShell, no `netsh`, no WMI, no elevation.
- Every rule on this machine carries `Action` (`Allow`/`Block`), `Dir`
  (`In`/`Out`) and `Name`; the parser reports all three for all 795
  (asserted by a live test, so a future store shape that drops one fails
  loudly instead of lying quietly).
- **Fields the parser does not model appear in the wild**: the wireless
  display rules carry `TTK2_22=WFDPrint` -- kept verbatim under
  `other_fields`, never dropped (unit-tested with the real string shape).

## What a real store looks like through the tools

- `win_firewall_table({})`: **0.063 s**, 100 rows (the default limit of a
  795-rule store), 3 profile rows, honest notes.
- **Built-in names resolve**: 508 of 795 rules name themselves indirectly
  (`@FirewallAPI.dll,-32757`); `SHLoadIndirectString` resolved **489
  in-process** to the machine's own language (Chinese here), the remaining
  **19 stayed as raw references** -- the fallback path is exercised by real
  data, not just by a unit test.
- `win_firewall_detail` by full id: **0.058 s** including a fresh sweep. The
  sample sentence reads "allows inbound traffic, in the private profile" for
  a capability rule that carries no protocol at all -- absence survives the
  sentence builder instead of crashing it.

## The three profiles, live

- On this build the profile keys sit **directly under `FirewallPolicy`**
  (`DomainProfile`, `PublicProfile`, `StandardProfile`); the Win7-era
  `...\FirewallPolicy\Profiles\` parent path does not exist here. The reader
  goes to the direct keys.
- Each profile key carries only what policy wrote: on this machine just
  `EnableFirewall=1` and `DisableNotifications=0`. `DefaultInboundAction` /
  `DefaultOutboundAction` are **absent** -- reported as `null` with the
  builtin-default note, not invented as numbers.
- The per-user rule store
  (`HKCU\Software\Microsoft\Windows\CurrentVersion\FirewallRules`) does not
  exist on this build: swept, reported empty, noted in the table.

## Cost

- Sweep 795 rules: 0.071 s. Table (sweep + sort + filter + note): 0.063 s.
  Detail (fresh sweep + match + full read): 0.058 s. The name resolver is
  cached per sweep: 489 resolutions land on ~450 unique references.

## Tests

21 pass on this machine: 15 unit (the parser with the real `v2.33` shapes
and the in-the-wild unknown key, the display resolver with hits, misses and
a cache, the profiles with mixed, absent and future values, the winreg-less
import behind a blocker, the table's filters and notes, the detail's
full-read, note and match matrices) + 6 live (the facts above, as
assertions).

## Admission validator

`hermes plugins validate` (via `hermes_cli.plugin_validate.validate_plugin_dir`)
on the working copy: **15/15 PASS, zero warnings, security scan safe** — the
exact gate the catalog runs on Linux CI, satisfied locally on Windows, with
the `winreg`-less import covered by a unit test for the platform the
validator actually runs on.

## Disclosure

The plugin reads the firewall's registry store (rule strings and profile
switches, machine hive plus the per-user key when it exists) and resolves
resource strings in-process to give built-in rules their display words. What
it reports: every rule's action, direction, protocol, ports, addresses,
program, service and name -- the same page Windows Security shows. Nothing
is enabled, disabled, added or removed; no network access; no file writes;
no elevation is requested or needed to read this store.
