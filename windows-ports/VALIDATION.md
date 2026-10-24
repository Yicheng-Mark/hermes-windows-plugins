# Validation

What was run, on what, and the numbers. Everything below comes from a real Windows machine.

## Environment

- Windows 11 Home China (10.0.26300), x64.
- Python 3.13, `pytest 9.1.1`.
- Hermes source for the admission check: the `main` tarball at the commit the check was run
  against, on `PYTHONPATH`; the check is repeated on the tarball of the pinned commit.

## Suites

| Command | Result |
|---|---|
| `python -m pytest tests -q` | 14 passed (12 unit + 2 live on Windows) |
| `python -m pytest tests -q` on a non-Windows interpreter | 12 passed, 2 skipped |

The unit suites drive the handler over a fake table: port and port-list filters, state
filtering, process substring matching, protocol selection, IPv6 exclusion, the record cap, the
empty-result note and the error path. Two decoding tests pin the byte-order handling for IPv4
addresses and ports.

The live suites bind a real listener on `127.0.0.1:<ephemeral>`, then find it again through
the tool and assert the PID is this process, and check that the table size is at least the
number of returned rows.

## Cross-check

`win_port_owners({"state": "listen"})` returned 8 listeners out of 121 table rows on the test
machine, including `0.0.0.0:135 -> pid 1912`, `0.0.0.0:5040 -> pid 4736`,
`192.168.0.198:139 -> pid 4 (System)` and four `127.0.0.1` listeners on one binary. The same
four rows appear in `netstat -ano` with the same PIDs.

A protected process whose image cannot be queried keeps its PID and reports
`process: null`; two of the eight rows on this machine are in that state, and the call still
returns normally.

## Official validator

`validate_plugin_dir` from the pinned commit's Hermes tree: **all checks pass, security scan
`safe`, no core override, zero warnings** — manifest, fields, `requires_hermes`, config
schema, `requires_env`, oauth, loadable, python dependencies, capability probe, declared
tools/hooks/middleware, built-in tool collisions, security scan, core override. Also run
against the tarball of the pinned commit.

## Disclosure

Read-only access to the TCP/UDP owner tables (`GetExtendedTcpTable`, `GetExtendedUdpTable`)
and image-name resolution through `QueryFullProcessImageName` with
`PROCESS_QUERY_LIMITED_INFORMATION`. The plugin does not open, bind or connect a socket, does
not read process memory, writes no files, starts no child processes, makes no network calls
and does not self-update. Tool output contains local and remote endpoints, PIDs and process
image paths, i.e. the information `netstat -ano` and Task Manager already show.
