# hermes-windows-ports

Answer **"who holds this port"** on Windows, from inside Hermes.

```python
win_port_owners({"port": 3000})
win_port_owners({"state": "listen", "process": "hermes"})
win_port_owners({"protocol": "tcp", "state": "established", "limit": 20})
```

`win_port_owners` reads the same tables `netstat -ano` prints — `GetExtendedTcpTable` /
`GetExtendedUdpTable` with the owning PID attached — and resolves each PID to its image name
through `QueryFullProcessImageName`. The result is structured JSON, not localized console
text, so it does not depend on the machine's display language.

```json
{
  "ok": true,
  "matched": 8,
  "listeners": 8,
  "total_endpoints": 121,
  "entries": [
    {"protocol": "tcp", "address": "127.0.0.1", "port": 8086, "state": "listen",
     "pid": 496, "process": "fc-core.exe", "path": "C:\\...\\fc-core.exe",
     "remote_address": "0.0.0.0", "remote_port": 0}
  ],
  "by_process": {"fc-core.exe": 4, "System": 1},
  "notes": ["8 endpoint(s) matched out of 121 in the table"]
}
```

## Why this exists

Port conflicts are one of the most common ways an agent stalls on Windows: a gateway, a
backend or a bridge cannot bind, and the error text names a port but not the process holding
it. The obvious workaround — running `netstat -ano` through the terminal tool — has two
problems: its output is localized (so parsing column headers breaks on a non-English machine),
and the PID it prints has to be resolved to a name by a second command whose output is
localized in the same way.

This plugin does the lookup once, in-process, and returns fields instead of columns. It is the
read-only half of the same question whether you are debugging `EADDRINUSE`, hunting a stale
process that survived a crash, or checking that only `127.0.0.1` is listening.

## Requirements

- Windows 10 or 11.
- Hermes 0.21.4 or newer.
- Nothing else: stdlib only (`ctypes`), no Python dependencies, no child processes, no network.

## Install

```bash
git clone --depth 1 https://github.com/Yicheng-Mark/hermes-windows-plugins /tmp/hermes-windows-plugins
cp -r /tmp/hermes-windows-plugins/windows-ports ~/.hermes/plugins/hermes-windows-ports
hermes plugins enable hermes-windows-ports
```

## Filters

| Argument | Meaning |
|---|---|
| `port` / `ports` | One port or several, matched on the local endpoint |
| `process` | Case-insensitive substring of the image name or path |
| `protocol` | `tcp`, `udp` or `both` (default) |
| `state` | `listen`, `established`, any TCP state name, or `all` (default); UDP rows report `bound` |
| `include_ipv6` | Read the IPv6 tables too (default true) |
| `limit` | Maximum endpoints returned (default 100, max 500) |

## Behaviour and limits

- Read-only. No socket is opened or bound, no connection is made.
- Some system processes (`pid 4` = System, `pid 0` = System Idle) are labelled; a protected
  process whose image cannot be queried keeps its PID and reports `process: null` instead of
  failing the whole call.
- `by_process` summarises the returned rows so a caller can see at a glance that, say, four
  listeners belong to one binary.
- Windows only. Other platforms get a structured error.

## Disclosure

- **Reads the local TCP/UDP tables and resolves PIDs to image paths.** Output includes local
  and remote addresses, ports, PIDs and process image paths — the same information
  `netstat -ano` plus Task Manager shows. Treat it like any other local diagnostic output.
- **No network activity.** The plugin does not open, bind or connect a socket; it only reads
  the kernel's tables.
- **Read-only process access.** `QueryFullProcessImageName` with
  `PROCESS_QUERY_LIMITED_INFORMATION` — the minimum right needed to read an image name. No
  memory reads, no handles inherited, no injection.
- **No child processes, no files written, no self-update.** Stdlib only (`ctypes`).

## Tests

```bash
python -m pytest tests -q
```

14 tests: filters, protocol/state handling, limits and error paths against a fake table on
every platform, plus live tests on Windows that bind a socket and find it again through the
tool, and cross-check the table size. See [VALIDATION.md](VALIDATION.md).

## License

MIT.
