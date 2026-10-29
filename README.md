# hermes-windows-plugins

Hermes plugins for the Windows-specific failures that do not happen on macOS or Linux:
processes that survive a quit, WSL interop, crash forensics, port ownership, and provider
keys stored somewhere better than a plaintext file.

Each subdirectory is a complete, standalone plugin, listed separately in the Hermes plugin
catalog — the entries point here with a `subdir:` instead of one repository per plugin.
Nothing is shared between the plugins at runtime: every one installs on its own, declares
its own capabilities, and pins its own version.

| Subdirectory | Catalog name | Kind | Answers |
|---|---|---|---|
| [`windows-ops/`](windows-ops/) | `hermes-windows-ops` | skill | Triage for processes that survive a quit, WSL→Windows argument mangling, UTF-8 BOM and code-page failures, long paths, console traps |
| [`wslc-sandbox/`](wslc-sandbox/) | `hermes-wslc-sandbox` | terminal backend (`wslc`) | Run terminal, file and `execute_code` tools in a WSL Containers sandbox, no Docker Desktop |
| [`wsl-terminal/`](wsl-terminal/) | `hermes-wsl-terminal` | terminal backend (`wsl`) | Run terminal tools inside a WSL distro you already have, with the cwd marker fixed for WSL |
| [`wincred/`](wincred/) | `hermes-wincred` | secret source | Resolve provider keys from the current user's Windows Credential Manager |
| [`dpapi-secrets/`](dpapi-secrets/) | `hermes-dpapi-secrets` | secret source | Resolve provider keys from one DPAPI-encrypted file instead of `.env` |
| [`windows-eventlog/`](windows-eventlog/) | `hermes-windows-eventlog` | tools | `win_crash_events`, `win_shutdown_events`, `win_eventlog_query` — why a process died, decoded |
| [`windows-ports/`](windows-ports/) | `hermes-windows-ports` | tools | `win_port_owners` — which process holds a port, with PID, image name and path |
| [`windows-process/`](windows-process/) | `hermes-windows-process` | tools | `win_process_table` — what is running, who started it, and what outlived its parent |
| [`windows-tasks/`](windows-tasks/) | `hermes-windows-tasks` | tools | `win_scheduled_tasks`, `win_scheduled_task_detail` — what the machine schedules on its own, when it runs next, and what its last result code meant |
| [`windows-services/`](windows-services/) | `hermes-windows-services` | tools | `win_service_table`, `win_service_detail` — what runs as a service, why one failed, and what it depends on |
| [`windows-devices/`](windows-devices/) | `hermes-windows-devices` | tools | `win_device_table`, `win_device_detail` — which device is unhappy, what it needs, and what drives it |

Every plugin is read-only where the platform allows it, stdlib-only (`ctypes` against
`advapi32`, `crypt32`, `wevtapi`, `iphlpapi`), and starts no child processes unless the
subdirectory's own README says otherwise. Each README carries the details, the exact
config keys, and the disclosures for what leaves the machine.

## Layout

```
windows-ops/         portable plugin: plugin.json + skills/
wslc-sandbox/        code plugin: plugin.yaml + hermes_wslc_sandbox/ + tests/
wsl-terminal/        code plugin: plugin.yaml + hermes_wsl_terminal/ + tests/
wincred/             code plugin: plugin.yaml + hermes_wincred/ + tests/
dpapi-secrets/       code plugin: plugin.yaml + hermes_dpapi_secrets/ + tests/
windows-eventlog/    code plugin: plugin.yaml + hermes_windows_eventlog/ + tests/
windows-ports/       code plugin: plugin.yaml + hermes_windows_ports/ + tests/
windows-process/     code plugin: plugin.yaml + hermes_windows_process/ + tests/
windows-tasks/       code plugin: plugin.yaml + hermes_windows_tasks/ + tests/
windows-services/    code plugin: plugin.yaml + hermes_windows_services/ + tests/
windows-devices/     code plugin: plugin.yaml + hermes_windows_devices/ + tests/
```

A catalog entry names the subdirectory it installs, for example:

```yaml
repo: https://github.com/Yicheng-Mark/hermes-windows-plugins
subdir: windows-ports
```

Tests run per plugin, from its own subdirectory (`python -m pytest` in `tests/` for the
code plugins). The live tests touch the real Windows API — Event Log, `netstat` owner
tables, Credential Manager, DPAPI, WSL — and skip themselves when the platform lacks it.

## History

These plugins lived in one repository each until 2026-10-25. Their content did not change
when they moved here: each subdirectory is the old repository root, minus its `.github/`
and `.gitattributes`, which mean nothing inside a subdirectory.

## License

MIT. See [`LICENSE`](LICENSE) — the same MIT text each plugin shipped with.
