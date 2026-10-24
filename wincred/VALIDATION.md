# Validation

What was actually run, on what, and what the numbers were. Everything below comes from a
real Windows machine, not from a mock of the OS API.

## Environment

- Windows 11 Home China (10.0.26300), x64.
- Python 3.13.15, `pytest 9.1.1`, `psutil 7.2.2` (needed by the Hermes validator tree).
- Hermes source: `main` at `2e83e2a935ee04f606aab58e498d34ca58d84c07` (2026-10-19), fetched
  as a tarball and put on `PYTHONPATH` for the contract tests and the official validator.

## Suites

| Command | Result |
|---|---|
| `python -m pytest tests/test_config.py tests/test_decode.py -q` | 12 passed |
| `PYTHONPATH=<hermes> python -m pytest tests -q` | 23 passed, 4 skipped (live opt-in) |
| `PYTHONPATH=<hermes> HERMES_WINCRED_LIVE=1 python -m pytest tests/test_live_wincred.py -q` | 4 passed |
| `cmdkey /list` after the live run | no `hermes-wincred-test/*` entries left |

Live tests create a uniquely named generic credential (`hermes-wincred-test/<uuid>`),
read it back through the plugin path, and delete it in fixture teardown.

## Official validator

`hermes_cli.plugin_validate.validate_plugin_dir()` on this tree:

```
ok = True
warnings = []
manifest                True  plugin.yaml parses
manifest fields         True  name, version, description present
requires_hermes         True  spec '>=0.21.4' parses
config schema           True  not declared
requires_env            True  all entries UPPER_SNAKE
loadable                True  entry: __init__.py
python dependencies     True  none declared
capability probe        True  register() ran in isolation
declared tools          True  matches registrations
declared hooks          True  matches registrations
declared middleware     True  matches registrations
built-in tool collisions True no tools to check
security scan           True  safe
no core override        True  no runtime rebinds of Hermes core
```

Catalog CI runs the same check against the tree at the pinned commit.

## Measured facts behind the design

- **`cmdkey` stores UTF-16LE.** A 15-character secret written with
  `cmdkey /generic:... /pass:...` comes back as a 30-byte blob with a NUL in every second
  byte; `decode_secret()` returns the plain key. The Credential UI and PowerShell follow
  the same encoding, while most CLI writers use UTF-8 — hence the two-encoding decoder.
- **Reads are cheap.** 200 consecutive `CredReadW` calls on a seeded credential took
  9.0 ms total (≈0.045 ms per read), so a startup fetch over a handful of mapped names is
  well below any perceptible cost and needs no cache.
- **Missing targets are distinguishable.** `CredReadW` fails with
  `ERROR_NOT_FOUND` (1168), which the source turns into a per-variable warning; the fetch
  as a whole only errors when *no* mapped credential could be read.

## Failure-mode decisions

- **Fail closed on undecodable blobs.** A blob that is neither UTF-8 nor plausible
  UTF-16LE (or that contains interior NULs, which an environment variable cannot carry)
  is skipped with a warning. A mangled API key is worse than no key.
- **Per-variable warnings, not a global failure.** One wrong target name must not hide the
  other nine working secrets.
- **`fetch()` never raises.** Every read is wrapped; the outer guard converts an
  unexpected exception into `ErrorKind.INTERNAL` with the exception *type* only, never
  its message or any value.
- **Read-only package.** `CredWriteW` / `CredDeleteW` live only in `tests/`; the installed
  package can read the vault and nothing else. No `os.environ` writes, no cache files, no
  child processes, no network.

## Not tested here

- Non-generic credential types (domain credentials, certificates) — the plugin only asks
  for `CRED_TYPE_GENERIC`.
- Roaming/enterprise vaults where a policy blocks `CredReadW` for the current process; the
  code maps the resulting Win32 error to a warning, but no such machine was available.
- Multiplexed profiles: applying fetched values is the orchestrator's job
  (`agent.secret_sources.registry.apply_all`), and precedence is its contract, not this
  plugin's.
