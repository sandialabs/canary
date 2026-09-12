# Canary Distributed Resource Pool Server

## Overview

`canary-distributed-server` is the server-side component for managing a distributed pool of
machines used by Canary distributed test execution.

The server maintains a resource database of worker machines and exposes an HTTP API used by
Canary clients to:

- check resources out before running tests,
- check resources back in when tests complete,
- inspect pool state and active checkouts,
- and perform basic pool administration.

The server is intended to run as a small containerized web application. For local testing it
can be run with plain HTTP on `localhost`. For production deployment it should be placed behind
site-approved HTTPS, authentication, authorization, and network access controls.

The server does **not** automatically add its own host machine to the pool. Worker machines
must be added explicitly.

---

## Package Scope

This package contains only the server application:

- the FastAPI server (`app.py`),
- resource-pool state management logic (`rpool.py`, `dpool.py`),
- the administrative HTTP API,
- the browser-based web interface,
- and container support (`Containerfile`).

It does **not** include the Canary client plugin. Install the Canary client/plugin package
separately in the environment where Canary jobs are submitted.

---

## Quick Start (local, no container)

### 1. Install

```console
pip install -e ".[dev]"
```

### 2. Start the server

```console
canary-dist-server start \
  --state-dir /tmp/canary-distributed \
  --host 127.0.0.1 \
  --port 8000
```

### 3. Verify

```console
curl http://localhost:8000/health
# {"success":true,"status":"ok"}
```

### 4. Open the web interface

```
http://localhost:8000/ui
```

### 5. Add a worker machine

```console
canary-dist-server add-host \
  --server-url http://localhost:8000 \
  --host worker01 \
  cpus=8
```

Or use the web interface form.

---

## Server State

The server stores all state in a single directory (`--state-dir`). The directory contains:

| File | Description |
|------|-------------|
| `pool.json` | Machine database: hostnames, resources, tags, groups, and current slot counts |
| `transactions.jsons` | Newline-delimited JSON log of all checkout/checkin transactions |
| `canary_distributed.log` | Rotating server log (5 MB max, 3 backups) |

`pool.json` is written atomically (via `.tmp` rename) on every mutation. This directory should
be on persistent storage when running in a container.

Default container path: `/data/canary-distributed`

---

## Resource Model

Each machine in the pool has a set of typed resources. Each resource type is a list of
**instances**, where each instance has:

- `id` — a string identifier (e.g. `"0"`, `"1"`, ...)
- `slots` — number of available allocation units (normally `0` or `1`)

When `add-host` creates a machine with `cpus=8`, it creates 8 CPU instances each with `slots=1`.
Checkout decrements `slots` to `0` on acquired instances; checkin restores them to `1`.

A checkout request is a list of `{"type": "<rtype>", "slots": 1}` items — one item per unit
needed. To request 4 CPUs send four `{"type": "cpus", "slots": 1}` items.

---

## HTTP API Reference

All endpoints accept and return `application/json`. The server uses standard HTTP status codes:
`200 OK`, `400 Bad Request`, `404 Not Found`, `409 Conflict`.

Every response body includes `"success": true/false` and a `"transaction_id"` UUID (a unique
identifier for the server-side operation; not a checkout transaction ID except on `/checkout`).

### `GET /health`

Health check. Returns `200` when the server is running.

**Response**
```json
{"success": true, "status": "ok"}
```

---

### `GET /status`

Returns the full machine database as JSON.

**Response**
```json
{
  "success": true,
  "transaction_id": "<uuid>",
  "database": {
    "machines": [
      {
        "hostname": "worker01",
        "state": "online",
        "resources": {
          "cpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 0}],
          "gpus": [{"id": "0", "slots": 1}]
        },
        "tags": ["gpu"],
        "groups": ["teamA"]
      }
    ]
  }
}
```

---

### `POST /add_host`

Add a worker machine to the pool.

**Request body**
```json
{
  "hostname": "worker01",
  "resources": [
    {"type": "cpus", "count": 8},
    {"type": "gpus", "count": 2}
  ],
  "state": "online",
  "tags": ["gpu"],
  "groups": ["teamA"]
}
```

- `hostname` — required, must be unique in the pool.
- `resources` — required, must include at least one `cpus` entry.
- `state` — optional; one of `online` (default), `offline`, `maintenance`.
- `tags` — optional list of strings. Checkout callers can require all tags to match.
- `groups` — optional list of strings. Checkout callers can require any group to match.

**Response** `200`
```json
{"success": true, "message": "Host worker01 added to distributed resource pool", "transaction_id": "..."}
```

**Errors**: `400` if hostname already exists or `cpus` is missing.

---

### `POST /remove_host?hostname=<hostname>`

Remove a machine from the pool entirely.

**Response** `200`
```json
{"success": true, "message": "Removed worker01 from the distributed resource pool", "transaction_id": "..."}
```

**Errors**: `404` if hostname not found.

---

### `POST /take_offline?hostname=<hostname>`

Set a machine's state to `"offline"`. The machine will be skipped for new checkouts.

**Response** `200`
```json
{"success": true, "message": "Took worker01 offline", "transaction_id": "..."}
```

**Errors**: `404` if hostname not found.

---

### `POST /bring_online?hostname=<hostname>`

Set a machine's state to `"online"`.

**Response** `200`
```json
{"success": true, "message": "Brought worker01 online", "transaction_id": "..."}
```

**Errors**: `404` if hostname not found.

---

### `POST /accommodates`

Check whether any online machine currently has enough free resources to satisfy a request,
without actually reserving anything.

**Request body**
```json
{
  "resources": [
    {"type": "cpus", "slots": 1},
    {"type": "cpus", "slots": 1}
  ]
}
```

**Response** `200`
```json
{
  "success": true,
  "accommodates": true,
  "reason": null,
  "transaction_id": "..."
}
```

If `accommodates` is `false`, `reason` explains why (e.g. `"Resource requirements could not be accommodated"`).

---

### `POST /checkout`

Reserve resources on the best available machine.

The server selects the online machine that satisfies the request **and** leaves the most
residual capacity (best-fit by Euclidean norm of remaining slot counts). Machines that do
not match all required `tags` or do not belong to any required `groups` are skipped.

**Request body**
```json
{
  "resources": [
    {"type": "cpus", "slots": 1},
    {"type": "cpus", "slots": 1},
    {"type": "gpus", "slots": 1}
  ],
  "timeout": 3600,
  "tags": ["gpu"],
  "groups": ["teamA"]
}
```

- `resources` — list of resource items to acquire.
- `timeout` — seconds until the checkout expires (used by `rx` to reclaim stale checkouts).
- `tags` — optional; all tags must be present on the selected machine.
- `groups` — optional; at least one group must match.

**Response on success** `200`
```json
{
  "success": true,
  "message": "resources acquired",
  "hostname": "worker01",
  "resources": {
    "cpus": [{"id": "3", "slots": 1}, {"id": "5", "slots": 1}],
    "gpus": [{"id": "0", "slots": 1}]
  },
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response when no machine is available** `200`
```json
{"success": false, "message": "resources unavailable"}
```

The `transaction_id` in the success response **must be supplied to `/checkin`** when resources
are released.

---

### `POST /checkin`

Release previously reserved resources and return them to the pool.

**Request body**
```json
{"transaction_id": "550e8400-e29b-41d4-a716-446655440000"}
```

**Response** `200`
```json
{"success": true, "message": "Resources returned to pool", "transaction_id": "..."}
```

**Errors**:
- `404` if the transaction ID is not found.
- `409` if the transaction has already been checked in (prevents double-release).

---

### `POST /rx`

Expire and reclaim all checkouts whose `timeout` has passed. Call this periodically (e.g.
from a cron job or monitoring script) to reclaim resources from crashed or lost clients.

**Response** `200`
```json
{"success": true, "transaction_id": "..."}
```

---

### `POST /restore_slots`

Force all resource slots on all machines back to `1` (fully available). Use with caution:
this invalidates active checkout accounting.

**Response** `200`
```json
{"success": true, "transaction_id": "..."}
```

---

### `POST /reset_db`

Wipe the machine database and transaction log. Requires confirmation.

**Request body**
```json
{"confirm": "RESET"}
```

**Response** `200`
```json
{"success": true, "message": "Resource pool and transaction log reset", "transaction_id": "..."}
```

**Errors**: `400` if `confirm` is not exactly `"RESET"`.

---

### `GET /ui_state`

Returns a JSON summary of the current pool state, suitable for the web interface polling loop.
Includes per-machine resource summaries and active (unchecked-in) transactions.

---

### `GET /ui` and `GET /`

Returns the self-contained HTML admin web interface.

---

## Web Interface

The server provides a minimal web interface at `http://<host>:<port>/ui`. It refreshes
automatically every 10 seconds.

Features:

- View all machines and their free/used resource counts.
- View active checkouts with expiry times and user/host info.
- Add machines using the form (`hostname` + `resources` in `type=N` format, e.g. `cpus=32,gpus=4`).
- Take machines offline or bring them back online.
- Remove machines.
- Restore all slots.
- Reset the database (requires typing `RESET` in a prompt).

---

## CLI Reference

The `canary-dist-server` command provides subcommands for server management and pool
administration. Client subcommands communicate with a running server; set
`CANARY_DISTRIBUTED_URL` to avoid passing `--server-url` every time.

```console
export CANARY_DISTRIBUTED_URL=http://localhost:8000
```

### `canary-dist-server start`

Start the server.

```
canary-dist-server start [options]

Options:
  --state-dir DIRNAME   State directory for pool.json, transactions, and logs
                        [default: system temp dir]
  --host HOST           Interface to bind [default: 0.0.0.0]
  --port PORT           Port to bind [default: 8000]
  --ssl-certfile FILE   TLS certificate file (requires --ssl-keyfile)
  --ssl-keyfile FILE    TLS private key file (requires --ssl-certfile)
```

Example:
```console
canary-dist-server start --state-dir /var/lib/canary-dist --host 0.0.0.0 --port 8000
```

### `canary-dist-server add-host`

Add a worker machine to the pool.

```
canary-dist-server add-host --server-url URL --host HOST [--tags TAGS] [--groups GROUPS] TYPE=N [TYPE=N ...]

Options:
  --host HOST       Hostname of the machine to add (required)
  --tags TAGS       Comma-separated tags (e.g. gpu,fast)
  --groups GROUPS   Comma-separated groups (e.g. teamA,teamB)

Positional:
  TYPE=N            Resource type and count, e.g. cpus=48 gpus=4
```

Examples:
```console
canary-dist-server add-host --host worker01 cpus=48
canary-dist-server add-host --host worker02 cpus=48 gpus=4 --tags gpu --groups teamA
```

### `canary-dist-server remove-host`

Remove a machine from the pool.

```
canary-dist-server remove-host --server-url URL --host HOST
```

### `canary-dist-server take-offline`

Take a machine offline (skipped for new checkouts).

```
canary-dist-server take-offline --server-url URL --host HOST
```

### `canary-dist-server bring-online`

Bring an offline machine back online.

```
canary-dist-server bring-online --server-url URL --host HOST
```

### `canary-dist-server status`

Print the pool database in YAML format.

```
canary-dist-server status --server-url URL
```

### `canary-dist-server restore-slots`

Restore all resource slots to 1 (fully available).

```
canary-dist-server restore-slots --server-url URL
```

### `canary-dist-server rx`

Expire and reclaim all stale (timed-out) checkouts.

```
canary-dist-server rx --server-url URL
```

---

## Building the Container

### Without a site certificate

For builds where no custom CA certificate is needed, comment out or remove the
`CERT_FILE` argument section from the `Containerfile` and update the `ENV` lines
for `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE`.

### With a site certificate

The `Containerfile` requires a certificate file supplied via a build argument:

```console
podman build \
  --build-arg CERT_FILE=certs/my-ca.crt \
  -f Containerfile \
  -t canary-distributed-server:latest .
```

---

## Running the Container

### Basic run

```console
mkdir -p dpool-data

podman run --rm \
  -p 8000:8000 \
  -v "$PWD/dpool-data:/data/canary-distributed:Z" \
  canary-distributed-server:latest
```

Open the web interface: `http://localhost:8000/ui`

Check health: `curl http://localhost:8000/health`

### Custom host port

```console
podman run --rm \
  -p 9000:8000 \
  -v "$PWD/dpool-data:/data/canary-distributed:Z" \
  canary-distributed-server:latest
```

### Custom state directory inside the container

```console
podman run --rm \
  -p 8000:8000 \
  -v "$PWD/dpool-data:/state:Z" \
  canary-distributed-server:latest \
  start --state-dir /state --host 0.0.0.0 --port 8000
```

### TLS termination in the container

Pass certificate and key files into the container and supply `--ssl-certfile` /
`--ssl-keyfile`:

```console
podman run --rm \
  -p 443:8443 \
  -v "$PWD/dpool-data:/data/canary-distributed:Z" \
  -v "$PWD/certs:/certs:Z,ro" \
  canary-distributed-server:latest \
  start \
    --state-dir /data/canary-distributed \
    --host 0.0.0.0 \
    --port 8443 \
    --ssl-certfile /certs/server.crt \
    --ssl-keyfile /certs/server.key
```

---

## Development

### Install editable with dev dependencies

```console
pip install -e ".[dev]"
```

Dev dependencies include `ruff` (lint/format), `ty` (type checker), `pytest`, and `httpx`
(required by the test client).

### Run tests

```console
pytest
```

Tests live in `tests/` and cover:

- `test_rpool.py` — `ResourcePool` unit tests (checkout, checkin, accommodates, rollback)
- `test_dpool.py` — `DistributedResourcePool` unit tests (multi-machine selection,
  persistence, tag/group filtering, live-state accommodates)
- `test_app.py` — full HTTP API tests via FastAPI `TestClient` (all endpoints, error paths,
  double-checkin guard, persistence across restarts, multi-machine scenarios)

### Lint and format

```console
ruff check src/ tests/
ruff format src/ tests/
```

---

## Production Deployment Notes

The server is intentionally simple. Production deployment should provide:

- HTTPS termination (either via `--ssl-certfile`/`--ssl-keyfile` or a reverse proxy),
- authentication and authorization (e.g. mTLS, API gateway, or network-level controls),
- network restrictions,
- service supervision and automatic restart,
- persistent storage for the state directory,
- and appropriate log aggregation.

Do not expose the administrative API or web interface broadly without access controls.
The `X-User` and `X-Host` request headers are informational only unless validated by
trusted infrastructure.

For periodic expiry reclamation, run `canary-dist-server rx` from a cron job or monitoring
script. The server does not reclaim expired checkouts automatically.

---

## Security Notes

The `/reset_db`, `/restore_slots`, `/add_host`, and `/remove_host` endpoints can materially
alter the pool. They require no authentication beyond network access in the default
configuration. Restrict access to trusted callers.

The double-checkin guard (`409 Conflict` on repeated `/checkin` calls for the same
transaction ID) prevents resource accounting from going above the original pool size.

The server runs as a non-root user (`UID 10001`) inside the container.
