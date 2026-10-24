# Validation record

Everything below was run on one machine. Commands are reproducible; measurements that depend
on this WSL version are called out.

## Environment

| | |
|---|---|
| OS | Windows 11 Home China 10.0.26300 |
| WSL | 3.0.3.0, kernel 6.18.54.1-1 |
| Distro | Ubuntu-24.04 (WSL 2), default user, one distro installed |
| Python | 3.13.15 (Windows), 3.12.3 (in the distro) |
| Hermes | `NousResearch/hermes-agent` at `75785989` (2026-10-11) — used for the contract check |
| Host locale | Chinese (this is why the localized-output checks exist) |

## Test results

```
$ python -m pytest tests/test_config.py tests/test_wsl_cli.py -q
59 passed

$ HERMES_WSL_LIVE=1 HERMES_SOURCE=D:\contrib\hermes-fresh python -m pytest tests/test_live_wsl.py -q
9 passed
```

The live suite creates a real `WslEnvironment` and asserts, through `wsl.exe`:

- commands run on Linux (`uname -s` is `Linux`), as the distro's user;
- the Windows cwd of the process is the project directory, translated (`pwd`);
- **the in-process translation agrees with the distro's own `wslpath -u`** for the project
  dir, the temp dir and `C:\Windows`;
- a file created on the Windows side is readable at its `/mnt/...` path — one file, not a copy;
- stdin is forwarded (`cat` with piped input);
- exit codes survive both the shell and `wsl.exe` (`exit 7` → `returncode == 7`);
- non-ASCII output round-trips (`中文 OK ✓`);
- `cd` in one command is the starting directory of the next;
- a per-call host `cwd` is translated.

## Finding: the stock cwd marker does not work under WSL

Hermes' base environment emits `printf '\n<marker>%s<marker>\n' "$(pwd -P)"` after every
command and reads `self.cwd` back from it. Under this WSL, **a forked-but-not-exec'd child is
given the directory `wsl.exe` started in**, not the shell's current one. A command
substitution is exactly such a child, so the marker reported the session's first directory
forever and `cd` never took effect.

Measured directly (`cd /tmp` first, then each probe):

| Probe | Reports |
|---|---|
| `pwd` (builtin, no subshell) | `/tmp` |
| `/bin/bash -c pwd` (fork + exec) | `/tmp` |
| `/bin/pwd -P` (external) | `/tmp` |
| `echo "$(pwd -P)"` (command substitution) | the starting directory |
| `echo "$PWD"` after `cd` | the starting directory |
| `/bin/sh -c 'printf "%s" "$(pwd -P)"'` | **still** the starting directory |

The last row is why "run it through one more shell" does not help: the wrong directory follows
the fork, not the program.

The backend therefore rewrites only the trailing marker (`WslEnvironment._wrap_command`) to
`printf '\n<marker>'; /bin/pwd -P | tr -d '\n'; printf '<marker>\n'` — three commands, no
subshell, both binaries from coreutils. If a future Hermes changes the marker's shape the
substitution does not match, the stock line is kept, and the backend degrades to "cwd does not
persist" rather than breaking. That is the only place the plugin touches a string the core
produces; nothing in `tools/` is patched at runtime.

## Admission validator

`hermes_cli.plugin_validate.validate_plugin_dir` (the code behind `hermes plugins validate`)
run against this directory with Hermes on `PYTHONPATH`:

```
OK= True
PASS manifest | plugin.yaml parses
PASS manifest fields | name, version, description present
PASS requires_hermes | spec '>=0.20.6' parses
PASS config schema | not declared
PASS requires_env | all entries UPPER_SNAKE
PASS loadable | entry: __init__.py
PASS python dependencies | none declared
PASS capability probe | register() ran in isolation
PASS declared tools | matches registrations
PASS declared hooks | matches registrations
PASS declared middleware | matches registrations
PASS built-in tool collisions | no tools to check
PASS security scan | safe
PASS no core override | no runtime rebinds of Hermes core
WARNINGS: []
```

## Contract check

```
$ python scripts/check_hermes_contract.py --hermes-source D:\contrib\hermes-fresh
PASS: installed Hermes interfaces match this plugin's contract.
```

That registers the provider in Hermes' real `agent.terminal_env_registry`, confirms
`plugin_backend_names()` lists `wsl`, and confirms `tools.terminal_tool_backends._create_environment`
routes the unknown backend name to this plugin.

## Provider smoke test against real Hermes

```
probe            ('ready', 'running in Ubuntu-24.04')
check_requirements({})  True
doctor rows      wsl.exe: C:\Windows\system32\wsl.exe
                 WSL version: WSL 版本: 3.0.3.0        (localized, reported verbatim)
                 WSL distros: Ubuntu-24.04
                 WSL backend distro: Ubuntu-24.04 (HERMES_WSL_DISTRO overrides)
flags            is_remote=True is_container=False skip_container_guards=False cache_path_base=None
```

## Not verified

- **More than one distro.** Only one is installed here. Selection is exercised in unit tests
  (`resolve_distro`), not against a live second distro.
- **`HERMES_WSL_USER`.** The distro has a single user; the `-u` argument is exercised in the
  argv shape, not against a second account.
- **A distro with a relocated automount root.** `wslpath -u 'C:\'` is parsed and the fallback
  path is unit-tested, but this distro uses the default `/mnt`.
- **Old WSL builds.** Version parsing is best-effort by design: `wsl --version` does not exist
  before WSL 1.x-era Windows builds, and the backend then simply reports no version rather than
  failing.
- **The Desktop app's backend picker.** The provider's `probe()` is what that picker calls; it
  was called directly, not through the Desktop UI.
- **Windows 10.** Everything above ran on Windows 11.

## `requires_hermes`

`>=0.20.6`, the version that carries the terminal-environment provider API this plugin is built
against (`ctx.register_terminal_environment_provider`, `BaseEnvironment`, `bash_argv`,
`_popen_bash`).
