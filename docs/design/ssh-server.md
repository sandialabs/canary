# `--connect=ssh://...`: implementation ideas

**Status**: not started, ideas only (2026-11-18).  Builds on the file-based server on `main`
(`64e8494c`); see `PLAN.md` in this directory for the server itself.

## Goal

```
on hpc-login, in the workspace:     canary server start
on a laptop with no shared FS:      canary --connect=ssh://hpc-login/scratch/ws run tests
                                    canary --connect=ssh://hpc-login/scratch/ws server wait ID
an agent:                           canary --connect=ssh://hpc-login/scratch/ws server post request.json
```

Same commands and semantics as `--connect=PATH`; only the transport differs.  `tests` is a
path on hpc-login.

## Core idea: no new protocol

The server's client CLI already speaks JSON and exit codes: `server post` (prints
`{"id": ...}`), `get` (JSON record), `wait` (streams output, exits with the command's code),
`cancel`, `status --json`.  An ssh transport runs *those same commands on the remote host*:

```
canary --connect=ssh://host/ws run tests
  -> ssh host canary --connect=/ws server post -        (request JSON on stdin) -> {"id": ...}

canary --connect=ssh://host/ws server wait ID
  -> ssh host canary --connect=/ws server wait ID       (output streams back; exit code passes through)
```

All files stay on the remote filesystem; the remote `canary` reads and writes them exactly as a
local client does today.  Nothing changes in the server.

## Design

### URL

`ssh://[user@]host[:port]/absolute/path[?cwd=DIR]`, parsed with `urllib.parse`.

* `host` is required (`ssh:///path` is an error).
* The path is WHERE on the remote host: the start of the remote workspace search, as for
  `--connect=PATH`.
* `cwd` (optional query) sets the request's working directory (see "Paths").

### A transport layer (first place it earns its keep)

Today `workspace_root(args)` resolves `--connect` to a local `Path` and the `server`
subcommands call `canary_server.requests` directly.  Introduce `canary_server/transport.py`
with two implementations of one small interface:

```python
class Transport(Protocol):
    def submit(self, request: dict) -> str: ...                      # -> id
    def get(self, request_id: str) -> dict: ...
    def wait(self, request_id: str, *, quiet: bool) -> int: ...      # streams, -> exit code
    def cancel(self, request_id: str) -> str: ...
    def status(self) -> dict: ...                                    # status --json
```

* `LocalTransport(root)`: today's code, moved behind the interface.
* `SshTransport(host, user, port, where, cwd)`: runs `ssh ... <remote canary>
  --connect=<where> server <sub> ...` via `subprocess`.

`--connect` parsing returns a transport; `canary_invoke_command` (the `--connect COMMAND` path)
and `ServerCommand.execute` dispatch through it.  `canary_cmdline_parse` (global options only)
is unchanged.  `server start` / `stop` stay local-only: you start a server where it runs.
(`stop` over ssh could be allowed later: it is just the `stop` sentinel.)

### Invoking the remote canary

```
ssh -o BatchMode=yes [-p PORT] [-l USER] HOST -- <remote command> --connect=<where> server <sub> <args>
```

* `BatchMode=yes`: never prompt for a password mid-command; fail fast instead.
* The remote command is one shell string; build it with `shlex.join` so args with spaces or
  quotes survive the remote shell.
* **Configurable remote command.**  A non-interactive `ssh host cmd` usually does not load the
  login profile, so `canary` may not be on `PATH` (and modules are not loaded).  Config, with a
  plain default:

  ```yaml
  server:
    ssh:
      command: "module load canary && canary"   # default: "canary"
      options: ["-o", "ControlMaster=auto", "-o", "ControlPersist=10m",
                "-o", "ControlPath=~/.ssh/cm-%r@%h:%p"]
  ```

  (`server:ssh:command` is a shell fragment run remotely; `options` are extra ssh arguments.)
* **Connection reuse.**  `wait`/`get` loops and repeated submissions pay a full ssh handshake
  each time; recommend (or default to) ControlMaster/ControlPersist via `options`.

### Paths and working directory (decided 2026-11-18)

* Path arguments are never rewritten, for any transport.
* Absolute paths must exist on the server's machine.  Relative paths resolve against the
  request's cwd, interpreted there.
* For ssh the client's directory means nothing remotely, so the request's `cwd` defaults to
  `"."` = the remote workspace anchor (same rule as `post`'s default).  Override with
  `?cwd=DIR` in the URL (relative to the anchor, or absolute), or `"cwd"` in `post` JSON.
* The server child already works on the server's workspace (`--canary-dir`), so
  `run --only=failed` and `run JOBID` behave as with `--connect=PATH`.

### Environment

Unchanged: requests run in the server's environment as of `server start`; nothing from the
client is carried; only an explicit `"env"` in `post`.  (The remote `canary` that *submits* runs
in the ssh session's environment, which is why `server:ssh:command` may need `module load`.)

### Streaming, exit codes, Ctrl-C

* `wait` streams the remote command's stdout/stderr as ssh relays them; the remote exit code is
  ssh's exit code.
* **Exit 255** is ssh's own failure (connection, auth).  Report it as such ("could not reach
  HOST: ..."), not as the request's result.  **127** usually means the remote `canary` was not
  found: point at `server:ssh:command`.
* **Ctrl-C.**  Without `-t`, ssh does not forward SIGINT to the remote process.  On
  `KeyboardInterrupt`, run a second `ssh HOST canary --connect=WHERE server cancel ID`, keep
  following until the request settles, and on a second Ctrl-C stop following (same behaviour as
  local `wait`).  Avoid `-t` (a tty mangles output and breaks piping).

### Liveness

The remote `canary` evaluates liveness itself (`live_server`): the same-host check if it runs
on the server's host, otherwise beat progress.  Nothing to change; the ssh client only sees the
remote answer (an ssh check may therefore take up to ~5 s when the ssh target is not the server
host).

### Version compatibility

The client and remote canary can differ.  Add `"protocol": 1` to the request (and to `status
--json`); the remote side rejects a protocol it does not know with a clear message.
`client_version` is already recorded for diagnosis.  Check once per invocation via
`status --json` (cheap with ControlMaster).

### Reads

`canary status`, `query`, `log`, `info` read the workspace directly and cannot over ssh.  Later,
`--connect=ssh://...` could forward read-only commands too (`ssh HOST canary -C ANCHOR status
...`) -- a pure passthrough, since they need no server.  Not needed for a first version; say so
in the docs.

### Security

No new attack surface: authentication and transport are ssh's.  Keep host-key checking at ssh's
defaults; never add `StrictHostKeyChecking=no`.  The remote side has the same permissions model
as today (who can write the workspace's `var/server/`).

## Testing

* **Fake ssh.**  Make the ssh executable configurable (`server:ssh:executable`, default `ssh`;
  tests point it at a tiny script that drops the ssh options and host and runs the command with
  `sh -c`).  That exercises URL parsing, quoting (`shlex.join`), stdin piping for `post -`,
  streaming, exit-code passthrough, 255/127 handling and the Ctrl-C -> remote cancel path,
  against a real local server, with no sshd.
* **Optional real ssh.**  An integration test against `localhost` that is skipped unless
  `ssh -o BatchMode=yes localhost true` succeeds.
* Unit tests for `SshTransport` command construction (exact argv) and URL parsing (user, port,
  query, missing host, relative path).

## Steps

1. `transport.py` with `LocalTransport`; route `--connect` and the `server` subcommands
   through it.  No behaviour change (existing tests are the safety net).
2. `SshTransport` + URL parsing + `server:ssh:{command,options,executable}` config; `post`,
   `get`, `wait`, `cancel`, `status` over ssh; `--connect=ssh://... COMMAND` submits with
   `cwd` defaulting to `"."`.  Fake-ssh tests.
3. Error handling (255/127), Ctrl-C -> remote cancel, `"protocol"` check.
4. Docs (server extension docs, `canary-server` skill, capabilities), including the
   ControlMaster recommendation and the "reads don't go over ssh yet" note.

Rough size: ~300 lines of code plus tests; steps 1-2 are most of it.

## Open questions

* Should `server stop` be allowed over ssh?  (Cheap: it is the sentinel; risky only by typo.)
* Default `cwd` for ssh: the anchor (proposed), or require `?cwd=` explicitly?
* Forward read-only commands (`status`, `query`, `log`) in the first version, or later?
* Default ControlMaster options on, or document them?
