# hermes-wincred

Resolve Hermes provider keys from the current user's **Windows Credential Manager** at
startup, instead of keeping them in plaintext in `~/.hermes/.env` or `auth.json`.

```yaml
# config.yaml
secrets:
  wincred:
    enabled: true
    map:
      ZAI_API_KEY: hermes/zai
      OPENAI_API_KEY: wincred://hermes/openai
```

Each mapped value is the **target name** of a generic credential. Hermes reads it once per
process, applies the value to the environment with its normal precedence and provenance,
and never writes the secret anywhere.

## Why this exists

Hermes already ships Bitwarden and 1Password sources and a generic command helper. On a
Windows desktop none of those is the natural store: there is no `pass`, and running a
vault CLI or a service account for one machine is more moving parts than the problem
deserves. Windows has had an OS-managed credential vault since Vista — Credential
Manager, per-user, DPAPI-protected, backed up with the user profile.

This plugin makes that vault a first-class `SecretSource`, so a provider key can live in
one place and be resolved by every Hermes process at startup. `auth.json` can then keep a
`env:ZAI_API_KEY` reference rather than the key itself.

## Requirements

- Windows 10 or 11.
- Hermes 0.21.4 or newer.
- Nothing else: stdlib only (`ctypes`), no Python dependencies, no child processes, no
  network calls.

## Install

```bash
hermes plugins install Yicheng-Mark/hermes-wincred
hermes plugins enable hermes-wincred
```

Then add the mapping to `config.yaml`:

```yaml
secrets:
  wincred:
    enabled: true
    map:
      ZAI_API_KEY: hermes/zai
      OPENAI_API_KEY: hermes/openai
```

## Storing a credential

Use the target name you put in `map` as the **generic credential** name.

**Credential Manager UI** (no shell history, no command line): open *Control Panel →
Credential Manager → Windows Credentials → Add a generic credential*, set the target
name to `hermes/zai`, any user name (it is ignored), and paste the key as the password.

**Command line** (note: the key becomes part of the shell history and of the process
command line while `cmdkey` runs):

```powershell
cmdkey /generic:hermes/zai /user:hermes /pass:sk-...
```

Check the names with `cmdkey /list`. To update a value, store it again with the same
target name; to remove one, `cmdkey /delete:hermes/zai`.

The value may be UTF-8 or UTF-16 (the Credential UI and PowerShell write UTF-16; most CLI
tools write UTF-8). Anything that does not decode as text is skipped with a warning
rather than injected as a mangled key.

## What it does at startup

For every entry in `map`, it calls `CredReadW` for a **generic** credential with that
target name in the current user's vault. Results are returned to the secret-source
orchestrator, which applies them like any other source:

- mapped sources beat bulk sources; within a shape, `secrets.sources` order decides;
- `override_existing` follows the standard `secrets.wincred` config key;
- provenance is reported as `(from Windows Credential Manager)`.

The plugin never writes `os.environ`, never caches values to disk, and never calls back
into Hermes outside the plugin API.

## Disclosure

- **Reads your credential vault.** Any Hermes process with the plugin enabled reads the
  current user's generic credentials named in `map`. It reads only the mapped targets —
  there is no enumeration of the vault.
- **Injects into the environment.** Resolved values become environment variables for the
  Hermes process and its children, exactly like a `.env` entry. Anything that can read
  the process environment (including shell commands you approve in the terminal tool)
  can see them; `secrets.<name>.override_existing` and the usual secret scrubbing rules
  are unchanged.
- **Not a boundary against same-user code.** Windows Credential Manager is DPAPI-backed
  and scoped to your user account. Another process running as you can read the same
  credentials. This raises the at-rest bar (backups, cloud sync, a `dotfiles` repo no
  longer carry the key in plaintext); it is not a sandbox.
- **Read-only.** The shipped package exposes `CredReadW` only. The tests carry their own
  `CredWriteW` helper to seed and delete a uniquely named credential.
- **No network, no subprocesses, no self-update.** Updates arrive only through the
  catalog pin and `hermes plugins update`.

## Limitations

- Windows only; on other platforms the source reports `BINARY_MISSING` and resolves
  nothing.
- Generic credentials only (not domain credentials or certificates).
- The credential blob is small by design (Windows caps it at 2,560 bytes); that is far
  larger than any API key.
- No caching: reads happen once per process at startup, in-process only.

## Development

```bash
python -m pytest tests/test_config.py tests/test_decode.py -q     # any platform
python -m pytest tests                                  -q         # needs Hermes core on PYTHONPATH
HERMES_WINCRED_LIVE=1 python -m pytest tests/test_live_wincred.py -q   # writes real credentials
```

`tests/test_source.py` and the live test import `agent.secret_sources.base` from a Hermes
checkout (`PYTHONPATH=/path/to/hermes-agent`); the catalog validator exercises the same
contract against the pinned tree. See [VALIDATION.md](VALIDATION.md) for the measurements
behind the encoding and failure-mode choices.
