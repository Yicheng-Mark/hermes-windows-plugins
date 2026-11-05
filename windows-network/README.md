# hermes-windows-network

Answer **"is this machine's network healthy, and which adapter is the problem"** on
Windows, from inside Hermes.

```python
win_adapter_table({})
win_adapter_table({"state": "disconnected"})
win_adapter_table({"virtual": True})
win_adapter_detail({"name": "WLAN"})
win_adapter_detail({"name": "以太网"})
```

"No internet" is several different problems wearing one outfit: a cable that is
unplugged, an adapter that was switched off, a DHCP server that never answered, a
gateway that is missing, DNS that cannot resolve. Windows shows all of these as
"no internet", and `ipconfig`'s prose follows the display language. These two tools
separate the cases and name them, in words that do not change with the language.

## What the tools report

| Field | Where it comes from |
|---|---|
| `state` | Up, Disconnected, Disabled, Not Present -- enum names, not localized words |
| `speed` | The link speed as a number (`2.5 Gbps`, `526.5 Mbps`), from the raw bits-per-second property |
| `virtual` | The adapter's own virtual flag, plus the product names in its description (Hyper-V, TAP, WireGuard...) |
| `mac`, `media_type` | As the adapter reports them |
| `driver` | Version and date of the adapter's driver |
| `ipv4` | Each address with its prefix and its origin (Dhcp, Manual, WellKnown) and whether it is link-local |
| `gateway4`, `dns4` | The default gateway and the DNS servers, IPv6 alongside |

`win_adapter_detail` adds the verdicts: **169.254.x.x** means DHCP did not answer and
Windows gave itself an address that reaches only its own subnet; an address without a
gateway cannot leave its subnet; no DNS servers means names will not resolve; a healthy
adapter has all three. A ghost adapter -- a radio or slot whose hardware is gone -- is
left out of the listing until `include_absent=true` asks for it.

## Read-only, and why it goes through the NetAdapter cmdlets

Nothing is enabled, renewed, reconfigured or released: the tools query, and the schemas
say so.

`ipconfig`'s output and `netsh`'s words follow the display language, which would make a
parser of them lie on every non-English machine. The `NetAdapter` and `NetTCPIP` cmdlets
answer through `ConvertTo-Json` with field names and enum values that do not ("Up",
"Disconnected"), while the adapter's own `Name` stays localized data ("以太网") that is
carried through, never parsed. The one trap this costs: `Get-NetIPConfiguration
-InterfaceIndex N` throws for an adapter IP is not bound to, so the detail call lists the
configurations once and filters, instead of asking for one index by parameter.

The link speed is read as the raw bits-per-second property rather than the display
string ("2.5 Gbps"), which also follows the display language.

## Cost

One PowerShell call for the listing (about **0.9 s** for 5 adapters on this machine) and
a second one only when a single adapter is asked for in detail. There is no cache: an
adapter's state changes exactly when a person is asking about it.

## Platform

Windows only. There are no Python dependencies, no network calls of its own and no
file writes.
