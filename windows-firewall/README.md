# hermes-windows-firewall

Answer **"what does the Windows firewall let through, and for whom"** on
Windows, from inside Hermes.

```python
win_firewall_table({"query": "python"})
win_firewall_table({"direction": "in", "active": True})
win_firewall_detail({"name": "NETDIS-SSDPSrv-Out-UDP-Active"})
```

The firewall question, answered without opening Windows Security: every rule
in the store the firewall service itself keeps, each row in plain words, plus
the three profile switches.

## What the tools report

| Field | Where it comes from |
|---|---|
| `id`, `name` | The rule's value name in the store; built-in names are `@FirewallAPI.dll,-N` references, resolved to the machine's own language in-process, unresolvable ones kept as the raw reference |
| `active` | `Active=TRUE/FALSE` -- a switched-off rule matches nothing, and says so |
| `action`, `direction` | `Allow/Block`, `In/Out`, enum-shaped words that do not translate |
| `protocol` | The number Windows stores (`6`, `17`, `47`) named (`TCP`, `UDP`, `GRE`); unknown numbers stay numbers |
| `local_ports`, `remote_ports` | As written: `2869`, `1024-65535`, `any` |
| `program`, `service` | The rule's `App`/`Svc` scope; `%SystemRoot%` expanded, the raw form kept beside it; a service rule's svchost is called out as the host, not the actor |
| `profiles` | `Domain`, `Private`, `Public` or `any` (the store writes `StandardProfile` where the UI says Private) |

`win_firewall_detail` adds the sentence of what the rule does, addresses with
scope words (the local subnet, any address), edge traversal, the embedding
group and description in the machine's language, and every field the parser
does not model -- passed through verbatim rather than dropped (`TTK2_22` is
on real machines).

The three profile rows carry each profile's firewall switch and default
actions. A value the registry did not write is `null`: Windows then applies
its builtin default (firewall on, inbound blocked, outbound allowed), which
the tools attribute as the default it is, never as a measured fact.

## Read-only, and why it goes through the registry

Nothing is enabled, disabled, added or removed: the tools enumerate registry
values and resolve resource strings; there is no firewall call at all.

The registry answers in hundredths of a second on this machine (795 rules in
0.07 s). `netsh advfirewall` labels its output in the machine's display
language -- a Chinese Windows prints Chinese value words -- so parsing it
means parsing a locale that changes with the install. The store under
`HKLM\SYSTEM\...\FirewallPolicy` is where the firewall service itself keeps
the rules, and its data either is enum-shaped or is the user's own words.

## Windows only

The plugin imports nowhere but on Windows: `winreg` is guarded, and on a
machine without it the tools answer with a clear error instead of crashing.
Windows-only is declared in the manifest.

## Testing

`python -m pytest tests/` -- unit tests fake the registry through an injected
opener, the display-word resolver through an injected loader, and the
`winreg`-less import behind a blocker; live tests check the real machine.
`VALIDATION.md` records the evidence.
