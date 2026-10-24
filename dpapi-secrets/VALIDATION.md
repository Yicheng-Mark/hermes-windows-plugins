# Validation

Everything here was run on the machine that produced the pinned commit: Windows 11
(10.0.26300), Python 3.13.15, x64. Hermes core was the source tree of
`NousResearch/hermes-agent` at the commit this entry is based on.

## Test suites

| Suite | Result | Needs Hermes core |
|---|---|---|
| `tests/test_config.py` + `tests/test_store.py` | 17 passed | no |
| `tests/test_source.py` | 13 passed | yes (`PYTHONPATH`) |
| `tests/test_conformance.py` (repo's own `SecretSourceConformance`) | 10 passed | yes (`PYTHONPATH`) |
| `tests/test_live_dpapi.py` (real DPAPI, opt-in) | 6 passed | yes (`PYTHONPATH`) |

The store tests run against a reversible stand-in for DPAPI so the format and failure
handling are exercised on any platform; the live suite is the one that actually calls
`CryptProtectData` / `CryptUnprotectData`.

## Admission validator

`hermes_cli.plugin_validate.validate_plugin_dir()` against this tree:

```
ok = True
warnings = []
PASS manifest / manifest fields / requires_hermes / config schema / requires_env
PASS loadable (entry: __init__.py) / python dependencies (none)
PASS capability probe — register() ran in isolation
PASS declared tools / hooks / middleware (matches registrations)
PASS built-in tool collisions — no tools to check
PASS security scan — safe
PASS no core override
```

The same validator was run against the tree at the **pinned** commit (a tarball of that
exact SHA, not the working copy) and reported the same result. That is the tree a reviewer
and the catalog CI see.

## Measurements

200 protect+unprotect cycles of a realistic payload (`{"openai": …, "zai": …}`):

```
protect+unprotect   mean 0.255 ms   median 0.198 ms   max 4.868 ms
write+read store    mean 1.420 ms   median 1.265 ms   max 4.407 ms   (includes fsync + rename)
encrypted blob       317 bytes for two short keys
```

The startup cost is a single decrypt per process: comfortably inside the default 120 s
budget, and far below the point where caching would be worth the risk of holding a
decrypted copy around.

## Decisions and the evidence behind them

**User scope, never machine scope.** `CRYPTPROTECT_LOCAL_MACHINE` would make the file
readable by every account on the machine. The plugin never passes that flag and does not
expose it as an option — a secret store whose key is shared with every local user is not a
secret store.

**No optional entropy.** Extra entropy only helps if it is stored somewhere the encrypted
file is not, which on a single machine means another plaintext config value: the same
compromise you were defending against. The user profile binding already gives the property
people want, so the plugin does not offer a knob that mostly creates a false sense of
strength.

**A magic header, not bare ciphertext.** The file starts with `HERMES-DPAPI-1\n` before the
blob. DPAPI would reject a foreign file anyway, but with an opaque error; the header turns
"you pointed `file:` at the wrong path" into a message that says so. Covered by
`test_rejects_a_foreign_file` and `test_rejects_a_header_without_payload`.

**Atomic replace on write.** `mkstemp` in the destination directory, write, `fsync`,
`os.replace`. `test_a_failed_write_leaves_the_previous_store_intact` injects a failure into
encryption and asserts the previous store still decrypts and no temp file survives.

**Nothing in the runtime path writes.** The package's only writer is the CLI module, which
runs when the user invokes it; `fetch()` reads. This keeps the installed plugin's behaviour
read-only, matching the other secret sources.

**Failure taxonomy.** Missing or foreign file → `NOT_CONFIGURED`; a blob this user cannot
decrypt → `AUTH_FAILED`; a platform without DPAPI → `BINARY_MISSING`; an unexpected
exception anywhere inside `fetch()` → `INTERNAL`. Nothing raises out of `fetch()`, which
the conformance kit checks directly.

## Failure modes exercised

- header missing / header with no payload → `StoreFormatError`, reported as
  `NOT_CONFIGURED`;
- decrypted payload that is not JSON, or not a flat string map → `StoreFormatError`;
- tampered blob (single byte flipped) → `DpapiError`, and through the source
  `AUTH_FAILED` with no secrets injected;
- a store written under another Windows profile → same path as tampering: DPAPI refuses to
  unwrap it, and the source resolves nothing rather than guessing;
- mapped name absent from the store, or present with an empty value → warning naming the
  variable, other mappings still resolve;
- all mappings failing → `EMPTY_VALUE`, nothing injected;
- `available()` false (non-Windows) → `BINARY_MISSING`;
- malformed `secrets.dpapi` sections (`None`, a string, a list, an empty map) → a
  `FetchResult` with `NOT_CONFIGURED`, never an exception.

## Reproducing

```bash
python -m pytest tests/test_config.py tests/test_store.py -q
PYTHONPATH=/path/to/hermes-agent python -m pytest tests/test_source.py tests/test_conformance.py -q
PYTHONPATH=/path/to/hermes-agent HERMES_DPAPI_LIVE=1 python -m pytest tests/test_live_dpapi.py -q

PYTHONPATH=/path/to/hermes-agent python -c "
from pathlib import Path
from hermes_cli.plugin_validate import validate_plugin_dir
rep = validate_plugin_dir(Path('.'))
print(rep.ok, rep.warnings)
for name, ok, detail in rep.checks: print('PASS' if ok else 'FAIL', name, detail)
"
```
