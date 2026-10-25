# hermes-dpapi-secrets

Resolve Hermes provider keys from a **DPAPI-encrypted secret file** at startup, instead of
keeping them in plaintext in `~/.hermes/.env` or `auth.json`.

```yaml
# config.yaml
secrets:
  dpapi:
    enabled: true
    map:
      ZAI_API_KEY: zai
      OPENAI_API_KEY: dpapi://openai
```

The file holds one blob encrypted with the Windows Data Protection API, keyed by the
current user profile. Hermes decrypts it once per process, applies the mapped values to the
environment with its normal precedence and provenance, and never writes the secret anywhere.

## Why this exists

Hermes ships Bitwarden, 1Password and a generic command helper, and the catalog already has
vault backends. None of them answers the small case: *one machine, no vault service, and a
provider key that should not sit in a dotfile.* On Windows the OS already has the primitive —
DPAPI derives a key from your Windows profile, so a file encrypted with it is readable by
that user on that machine and by nothing else.

The alternative on this platform is [`hermes-wincred`](https://github.com/Yicheng-Mark/hermes-windows-plugins/tree/main/wincred),
which reads individual items from Credential Manager. The difference is where the secret
lives:

| | `dpapi` (this plugin) | `wincred` |
|---|---|---|
| Storage | one encrypted file you can back up, move or delete | one Credential Manager item per secret |
| Visible in the Windows UI | no | yes, in *Credential Manager → Windows Credentials* |
| Size per secret | whatever the file holds | capped by the credential blob (2,560 bytes) |
| Provisioning | `python -m hermes_dpapi_secrets set NAME` | Credential Manager UI or `cmdkey` |

Both are DPAPI-backed and user-scoped; pick the one whose storage model you want to live
with. `auth.json` can then keep an `env:ZAI_API_KEY` reference rather than the key itself.

## Requirements

- Windows 10 or 11.
- Hermes 0.21.4 or newer.
- Nothing else: stdlib only (`ctypes`), no Python dependencies, no child processes, no
  network calls.

## Install

```bash
hermes plugins install Yicheng-Mark/hermes-dpapi-secrets
hermes plugins enable hermes-dpapi-secrets
```

Then add the mapping to `config.yaml`:

```yaml
secrets:
  dpapi:
    enabled: true
    file: secrets.dpapi          # optional; relative to the Hermes home
    map:
      ZAI_API_KEY: zai
      OPENAI_API_KEY: dpapi://openai
```

## Creating the store

The runtime side is read-only. Provision the store with the bundled CLI, **as the same
Windows user that runs Hermes** — the encryption key belongs to that profile:

```bash
python -m hermes_dpapi_secrets set ZAI_API_KEY      # prompts; the value is not echoed
printf 'sk-...' | python -m hermes_dpapi_secrets set ZAI_API_KEY   # piped form
python -m hermes_dpapi_secrets list                 # names only, never values
python -m hermes_dpapi_secrets unset ZAI_API_KEY
python -m hermes_dpapi_secrets path                 # where the store lives
```

`--file` overrides the store path; by default it is `<HERMES_HOME or ~/.hermes>/secrets.dpapi`.
Values are never accepted on the command line (where they would reach the shell history and
the process table), never printed, and never written in plaintext.

## What it does at startup

For every entry in `map`, it decrypts the store once and hands the requested values to the
secret-source orchestrator, which applies them like any other source:

- mapped sources beat bulk sources; within a shape, `secrets.sources` order decides;
- `override_existing` follows the standard `secrets.dpapi` config key;
- provenance is reported as `(from Windows DPAPI secret file)`.

A name that is missing from the store, or that holds an empty value, is skipped with a
warning naming it; the other mappings still resolve. If nothing resolves, the source reports
an error and injects nothing. The plugin never writes `os.environ`, never caches values, and
never calls back into Hermes outside the plugin API.

## Security model

- **User scope only.** Blobs are protected with `CRYPTPROTECT_UI_FORBIDDEN` and *not* with
  the machine-wide flag. Machine scope would let any local account on the box decrypt the
  file; that is the wrong default for a secret store, so the option does not exist.
- **No prompt on the startup path.** `CRYPTPROTECT_UI_FORBIDDEN` means a locked or
  changed profile fails with an error rather than popping a dialog in a service context.
- **Fail closed.** A file without this plugin's header, a blob this user cannot decrypt, a
  decrypted payload that is not a flat string map — each is an error, never a partial guess.
- **Atomic writes.** The CLI writes a temporary file in the same directory and renames it
  into place, so an interrupted write cannot leave a truncated store.

## Disclosure

- **Decrypts a file for every Hermes process that enables the source.** The plaintext lives
  in the process environment of Hermes and its children exactly like a `.env` entry, for as
  long as the process runs.
- **Protects the file at rest, not a running session.** DPAPI raises the bar for backups,
  cloud sync, a stolen disk image or a `dotfiles` repo — the file is useless off this
  machine or to another Windows account. It is not a boundary against code already running
  as you: anything running in your session can call `CryptUnprotectData` on the same file.
- **The CLI writes; the runtime does not.** `python -m hermes_dpapi_secrets set` creates or
  updates the store on explicit user action. The installed plugin's `fetch()` only reads.
- **No network, no subprocesses, no self-update.** Updates arrive only through the catalog
  pin and `hermes plugins update`.

## Limitations

- Windows only; on other platforms the source reports `BINARY_MISSING` and resolves nothing.
- One store per Hermes home. Use `file:` to point a profile at a different store, or the
  `unset`/`set` commands to curate a single one.
- The store is not portable: copying it to another machine or another Windows account makes
  it unreadable by design. Re-create it there instead.
- No caching: the store is read once per process at startup, in-process only.

## Development

```bash
python -m pytest tests/test_config.py tests/test_store.py -q      # any platform
PYTHONPATH=/path/to/hermes-agent python -m pytest tests -q        # adds the contract suite
PYTHONPATH=/path/to/hermes-agent HERMES_DPAPI_LIVE=1 \
    python -m pytest tests/test_live_dpapi.py -q                  # writes real DPAPI blobs
```

`tests/test_source.py` and the live test import `agent.secret_sources.base` from a Hermes
checkout; `tests/test_conformance.py` runs the repository's own `SecretSourceConformance`
kit against this backend. The catalog validator exercises the same contract against the
pinned tree. See [VALIDATION.md](VALIDATION.md) for the measurements behind the format and
failure-mode choices.
