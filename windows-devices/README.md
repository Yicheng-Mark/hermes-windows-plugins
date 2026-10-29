# hermes-windows-devices

Answer **"which device on this machine is unhappy, and what does it need"** on Windows,
from inside Hermes.

```python
win_device_table({"broken_only": True})
win_device_table({"class": "net"})
win_device_detail({"name": "LENOVO"})
```

The Device Manager question, answered without Device Manager: a yellow mark on a device is
a number nobody translates, and these two tools translate it — `28` is no driver
installed, `10` cannot start, `43` Windows stopped it after it reported a failure, `22` is
switched off on purpose (not broken), `1` is configured incorrectly.

## What the tools report

| Field | Where it comes from |
|---|---|
| `name`, `manufacturer` | The device as Windows names it (localized, carried through, never parsed) |
| `class` | `PNPClass`: System, Net, HIDClass, Display, Camera, ... |
| `status`, `problem` | Status (OK/Error/Degraded) and the problem code with its meaning |
| `device_id` | The stable id, e.g. `PCI\VEN_8086&DEV_2723&...` — the match key for detail |
| present vs historical | Devices not plugged in any more are left out unless asked for |

`win_device_detail` adds the driver behind the device — name, version, date, provider,
signer, INF file, and whether it is signed — or the absence of one, which for problem
code 28 is the same fact said twice. A disabled device (code 22) gets a note saying it is
on purpose, not an alarm.

## Read-only, and why it goes through CIM

Nothing is enabled, disabled, updated or reinstalled: the tools query, and the schemas
say so.

Both answers come from CIM — `Win32_PnPEntity` for the tree (235 devices in 1.7 s on this
machine, unelevated) and `Win32_PnPSignedDriver` for the driver table (239 rows, 2.2 s,
joined by device id). Property names, enum values and ids do not change with the display
language; the human-facing `Name`/`Manufacturer` localize, but they are data carried
through, never parsed. One child process per query (`powershell.exe`, hidden window,
90 s timeout); no registry walk, no SetupAPI, no network, no file writes.

## Layout

```
plugin.yaml                       manifest: tools, tags, the read-only disclosure
hermes_windows_devices/
  tools.py                        the two tools: filtering, rows, notes
  devquery.py                     the two CIM calls (PowerShell, ConvertTo-Json)
  codes.py                        problem-code words
  schemas.py                      the tools' parameter schemas
tests/test_unit.py                the tools over faked CIM answers; no PowerShell
tests/test_live.py                the real device tree and driver table on this machine
```
