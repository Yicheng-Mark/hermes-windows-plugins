# hermes-wsl-terminal

Run Hermes' terminal tools inside a WSL distro you already have, instead of a Windows shell.

```yaml
# config.yaml
terminal:
  backend: wsl
```

One `bash -c` per command through `wsl.exe -d <distro>`, as the distro's normal user. No
container, no image, no Docker Desktop, nothing to start or tear down — the distro is already
installed and `wsl.exe` starts it on demand.

## Why this exists

Hermes on Windows runs its shell commands through Git Bash on the Windows filesystem. That is
the wrong environment for anyone whose toolchain lives in Linux: `apt`, `systemd`, a Linux
`node`/`python`/`git`, POSIX permissions and paths, a project checked out under `~/`.

The existing ways out are heavier than they need to be. The Docker backend needs Docker
Desktop and an image. The SSH backend needs an sshd inside the distro and a key. WSL Containers
(`wslc`) is a sandbox runtime that not every Windows build has. A WSL distro needs none of
that: it is already there, it boots on first use, and Windows drives are mounted inside it at
`/mnt/<drive>`, so the project you opened in Hermes is the same directory the commands run in.

## Requirements

- Windows 10/11 with WSL, and at least one distro (`wsl -l -q` lists one).
- Hermes 0.20.6 or newer.
- Nothing else. The plugin has no Python dependencies and makes no network calls.

## Install

```bash
hermes plugins install Yicheng-Mark/hermes-wsl-terminal
hermes plugins enable hermes-wsl-terminal
hermes config set terminal.backend wsl
```

Or clone it into `~/.hermes/plugins/hermes-wsl-terminal` and enable it.

## Configuration

Optional, both read at environment-creation time:

| Variable | Default | Meaning |
|---|---|---|
| `HERMES_WSL_DISTRO` | the distro `wsl` starts with | Which distro commands run in. |
| `HERMES_WSL_USER` | the distro's default user | Run as another user (`wsl -u`). |

The mount root is detected per distro with `wslpath`, so a distro that moved its automount
point in `/etc/wsl.conf` still gets correct paths.

## What the backend does

- **Path translation.** A Windows cwd is translated before the command runs: `C:\Users\me\proj`
  becomes `/mnt/c/Users/me/proj`, and `\\wsl.localhost\Ubuntu-24.04\home\me` becomes
  `/home/me`. Paths already written the Linux way pass through untouched.
- **cwd persistence.** `cd` in one command is the starting directory of the next, the way it
  works in a terminal.
- **stdin, timeouts and background processes** come from Hermes' shared environment plumbing,
  so they behave like the other spawn-per-call backends.
- **`hermes doctor`, `hermes setup` and the dashboard picker** get real rows from the backend:
  the `wsl.exe` path, the WSL version, the distros present, and which one is selected.

## What it does not do

- **No isolation.** Commands run as your user in your distro, with your files and your network.
  Destructive-command approval stays on; this is explicitly not a sandbox.
- **No container-style resource limits.** `container_*` settings do not apply to a distro.
- **It never stops the distro.** Teardown releases nothing on purpose: your other shells and
  services share it.
- **Files *inside* the distro are addressed by their UNC path from the Windows side.** File
  tools work on `\\wsl.localhost\<distro>\home\me\...`; the common case — a project on a
  Windows drive — needs no translation at all because `/mnt/<drive>` is the same directory.

## Disclosure

Installing this plugin adds a terminal backend. When it is the selected backend, everything
the model asks the `terminal` tool to run executes as your user inside your WSL distro, with
that distro's network access and file permissions. The plugin itself reads no credentials,
stores none, and makes no network calls; it spawns `wsl.exe` and, once per distro, `wslpath`.
It does not change any Hermes core behaviour: it registers a provider and returns an
environment object.

## Development

```bash
python -m pytest tests/test_config.py tests/test_wsl_cli.py   # no WSL or Hermes needed
python -m pytest tests/test_live_wsl.py                       # HERMES_WSL_LIVE=1 HERMES_SOURCE=/path/to/hermes-agent
python scripts/check_hermes_contract.py --hermes-source /path/to/hermes-agent
```

## Layout

```
hermes_wsl_terminal/config.py      path translation and CLI-output parsing (stdlib only)
hermes_wsl_terminal/wsl.py         wsl.exe calls (stdlib only)
hermes_wsl_terminal/environment.py BaseEnvironment: one bash -c per command
hermes_wsl_terminal/provider.py    registration, classification, probe, doctor rows
tests/                             stdlib tests, CLI-shape tests, live distro tests
scripts/check_hermes_contract.py   the plugin against a real Hermes checkout
```

The two stdlib modules carry the rules a reviewer needs to check — what a Windows path becomes
inside the distro, and how `wsl.exe`'s UTF-16 CLI output is decoded — and they are testable
without a Hermes install or a distro.
