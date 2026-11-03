# Validation

What was checked before this plugin was submitted, on which machine, and what the numbers
were. Everything below was run on Windows 11 (build 26300), Python 3.13, against the
`hermes-agent` admission validator from the 10-19 main tree.

## Admission checks

`validate_plugin_dir` reports all checks pass, security scan safe, on this directory. The
plugin suite is **17 passed** (12 unit, 5 live) on this machine; the same suite runs inside
the pin tarball before the entry is submitted.

## Why the dependencies come from the registry and not CIM

CIM's `Win32_Service.DependOnService` property exists but is never populated. Measured on
this machine (293 services):

```powershell
@((Get-CimInstance Win32_Service) | Where-Object {$_.DependOnService}).Count   # 0
sc.exe qc dnscache                                                             # DEPENDENCIES: nsi, Afd
```

The registry answers the same question the `sc` tool answers, unelevated, as a `MULTI_SZ`
at `HKLM\SYSTEM\CurrentControlSet\Services\<name>\DependOnService` (a `+` prefix names a
load-order group).

## Why `sc.exe` is not parsed at all

`sc query` and `sc qc` localize both their labels and status words with the display
language; `Get-CimInstance` answers property names and enum values that do not change
(`State` is `Stopped` on a Chinese install too). One CIM call lists all 293 services in
0.6 s, unelevated, including the state, start mode, delayed flag, pid, exit code, account,
binary path and description.

## The FailureActions blob, decoded

`FailureActions` at the same key is an undocumented binary value following the 32-bit
`SERVICE_FAILURE_ACTIONS` ABI: `DWORD` reset period, two `DWORD` string offsets, `DWORD`
count, a `DWORD` offset to the action array (20 in practice), then count × (`type`,
`delay_ms`) pairs. Decoded with `struct` only. Verified against `wuauserv`, whose 44-byte
blob reads back as reset-after-24 h and three "restart after 60 s" actions — exactly what
the Services snap-in shows:

```
80 51 01 00 | 00 00 00 00 | 00 00 00 00 | 03 00 00 00 | 14 00 00 00 | 01 00 00 00 60 EA 00 00 ...
 86400 s        -               -          3 actions     offset 20      restart, 60000 ms
```

## What a person sees

- `win_service_table` on this machine: 293 services registered, 160 running, 133 carrying
  a non-zero exit code (mostly `1077`, never started since boot — not failures; the filter
  and the notes say so).
- `win_service_detail({"name": "wuauserv"})`: start `Auto, delayed`, depends on `rpcss`,
  failure policy `restart after 60 s ×3, reset after 24 h`, binary present, the SCM event
  history behind it.
- `win_service_detail` on a service whose binary was uninstalled reports the exit code's
  meaning (`2`, the binary could not be found) and a note that the registered binary is no
  longer on disk.

## The review delta (after e278adf4)

Three fixes from the catalog review, each with a regression test:

- **The module imports where `winreg` does not exist.** The registry helpers took
  `opener: Callable = winreg.OpenKey` as a default argument — evaluated once at import
  time, so on a machine without `winreg` the import itself raised `AttributeError` and
  `hermes plugins validate` could not load the plugin. The defaults are now `None`
  sentinels resolved at call time (`_value` already did this). Test:
  `test_module_imports_where_winreg_does_not_exist` reloads the module with a meta-path
  blocker that raises on `import winreg`, asserts the import survives and that a registry
  read then raises `RegistryUnavailable` (an answer, not a crash).
- **Mixed-case service names keep their registry facts.** The detail tool looked the
  sweep up under `name.lower()` while the sweep keys by the registered spelling, so
  `Dhcp` lost its dependencies and delayed flag when asked for as `dhcp`. Live check
  after the fix: `win_service_detail({"name": "dhcp"})` reports `depends_on: NSI, Afd`.
- **`dependents` is computed from the full sweep.** It used to be derived from the one
  service's own facts, which can only ever be empty (a service's dependencies do not
  name itself). It now runs the same single sweep the table runs and answers who lists
  this service. Live check: `win_service_detail({"name": "dhcp"})` reports
  `dependents: WinHttpAutoProxySvc`, end to end in 0.85 s including the event log read.

After the delta: 20 tests pass (15 unit + 5 live, was 12 + 5), and the admission
validator is 15/15 PASS with zero warnings on the working copy.
