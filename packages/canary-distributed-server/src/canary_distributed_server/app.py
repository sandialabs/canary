#!/usr/bin/env python3
"""
Canary Distributed Resource Pool Server
Finalized version with:
- CLI work-dir argument
- PID file support
- JSON resource pool
- Transaction logging
- Thread-safe blocking
- FastAPI server
"""

import datetime
import json
import logging
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .dpool import DistributedResourcePool
from .rpool import ResourceUnavailable

# ----------------------------
# APP SETUP
# ----------------------------
db_lock = Lock()

MAX_LOG_SIZE = 5 * 1024 * 1024  #  5 MB
BACKUP_COUNT = 3


logger = logging.getLogger("canary_distributed")
logger.setLevel(logging.DEBUG)
handler = None  # initialized later after DB_DIR is known


class ResetDBRequest(BaseModel):
    confirm: str


class CheckoutRequest(BaseModel):
    resources: list[dict[str, Any]]
    timeout: float
    tags: list[str] | None = None
    groups: list[str] | None = None


class AccommodatesRequest(BaseModel):
    resources: list[dict[str, Any]]


class AddHostRequest(BaseModel):
    hostname: str
    resources: list[dict[str, Any]]
    state: str | None = None
    tags: list[str] | None = None
    groups: list[str] | None = None


class CheckinRequest(BaseModel):
    transaction_id: str


def make_fastapi(prefix: Path) -> "FastAPI":
    prefix = prefix.absolute()
    prefix.mkdir(parents=True, exist_ok=True)
    transactionsfile = prefix / "transactions.jsons"
    poolfile = prefix / "pool.json"
    logfile = prefix / "canary_distributed.log"

    if not logger.handlers:
        handler = RotatingFileHandler(logfile, maxBytes=MAX_LOG_SIZE, backupCount=BACKUP_COUNT)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    def load_transactions() -> list[dict]:
        transactions: list[dict] = []
        if transactionsfile.exists():
            with transactionsfile.open() as f:
                for line in f:
                    transactions.append(json.loads(line))
        return transactions

    def save_transactions(transactions, maxbytes: int | None = None) -> None:
        maxbytes = maxbytes or 10 * 1024 * 1024  # 10 Megabytes
        lines: list[str] = [json.dumps(t, separators=(",", ":")) for t in transactions]
        sizes: list[int] = [len(line.encode("utf-8")) for line in lines]
        total: int = 0
        start: int = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if total + sizes[i] > maxbytes:
                break
            total += sizes[i]
            start = i
        tmp = transactionsfile.with_suffix(".tmp")
        with tmp.open("w") as fh:
            for i, line in enumerate(lines):
                if transactions[i].get("checked_in") is None:
                    # Save any transactions not checked in
                    fh.write(line + "\n")
                elif i >= start:
                    fh.write("\n".join(lines[i:]) + "\n")
                    break
        tmp.replace(transactionsfile)

    def summarize_machine_resources(machine: dict[str, Any]) -> dict[str, dict[str, int]]:
        """
        Summarize resource free/used state for display.

        Assumes each resource instance was created with slots=1. The pool checkout
        logic decrements slots when reserved.
        """
        summary: dict[str, dict[str, int]] = {}

        for rtype, instances in machine.get("resources", {}).items():
            total_instances = len(instances)
            free_slots = 0
            used_slots = 0

            for instance in instances:
                slots = int(instance.get("slots", 0))
                free_slots += max(0, slots)
                used_slots += max(0, 1 - slots)

            summary[rtype] = {"instances": total_instances, "free": free_slots, "used": used_slots}

        return summary

    def active_transactions(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = datetime.datetime.now()
        active: list[dict[str, Any]] = []

        for transaction in transactions:
            if transaction.get("checked_in"):
                continue

            expires_raw = transaction.get("expires")
            expired = False
            if expires_raw:
                try:
                    expired = now > datetime.datetime.fromisoformat(expires_raw)
                except ValueError:
                    expired = False

            active.append(
                {
                    "id": transaction.get("id"),
                    "target_host": transaction.get("target_host"),
                    "resources": transaction.get("resources", {}),
                    "checked_out": transaction.get("checked_out"),
                    "expires": transaction.get("expires"),
                    "expired": expired,
                    "user": transaction.get("user", "unknown"),
                    "calling_host": transaction.get("calling_host", "unknown"),
                }
            )

        return active

    def build_ui_state() -> dict[str, Any]:
        pool = DistributedResourcePool(poolfile)
        transactions = load_transactions()

        machines: list[dict[str, Any]] = []
        for machine in pool.db.get("machines", []):
            machines.append(
                {
                    "hostname": machine.get("hostname"),
                    "state": machine.get("state", "online"),
                    "tags": machine.get("tags", []),
                    "groups": machine.get("groups", []),
                    "resource_summary": summarize_machine_resources(machine),
                    "resources": machine.get("resources", {}),
                }
            )

        return {
            "success": True,
            "machines": machines,
            "active_transactions": active_transactions(transactions),
            "transaction_count": len(transactions),
        }

    def log_request(
        endpoint: str, user: str | None = None, calling_host: str | None = None
    ) -> None:
        msg = f"Endpoint: {endpoint}"
        if user:
            msg += f", User: {user}"
        if calling_host:
            msg += f", Calling host: {calling_host}"
        logger.info(msg)

    app = FastAPI()

    # ----------------------------
    # MIDDLEWARE
    # ----------------------------
    @app.middleware("http")
    async def log_all_requests(request: Request, call_next):
        user = request.headers.get("X-User", "unknown")
        calling_host = request.headers.get("X-Host", "unknown")
        # body = await request.body()
        log_request(endpoint=str(request.url.path), user=user, calling_host=calling_host)
        response = await call_next(request)
        return response

    # ----------------------------
    # API ENDPOINTS
    # ----------------------------
    @app.post("/accommodates")
    def accommodates(request: AccommodatesRequest):
        transaction_id = str(uuid.uuid4())
        with db_lock:
            pool = DistributedResourcePool(poolfile)
            result = pool.accommodates(request.resources)
            return {
                "success": True,
                "accommodates": result.ok,
                "reason": result.reason,
                "transaction_id": transaction_id,
            }

    @app.post("/checkout")
    def checkout(payload: CheckoutRequest, http_request: Request):
        transaction_id = str(uuid.uuid4())
        user = http_request.headers.get("X-User", "unknown")
        calling_host = http_request.headers.get("X-Host", "unknown")

        with db_lock:
            pool = DistributedResourcePool(poolfile)
            transactions = load_transactions()

            try:
                hostname, acquired = pool.checkout(
                    payload.resources, groups=payload.groups, tags=payload.tags
                )
            except ResourceUnavailable:
                return {"success": False, "message": "resources unavailable"}
            else:
                pool.save()

            now = datetime.datetime.now()
            expires = now + datetime.timedelta(seconds=payload.timeout)
            transaction = {
                "id": transaction_id,
                "target_host": hostname,
                "resources": acquired,
                "checked_out": now.isoformat(),
                "checked_in": None,
                "expires": expires.isoformat(),
                "user": user,
                "calling_host": calling_host,
            }

            transactions.append(transaction)
            save_transactions(transactions)

            result = {
                "success": True,
                "message": "resources acquired",
                "resources": acquired,
                "hostname": hostname,
                "transaction_id": transaction_id,
            }
            return result

    @app.post("/checkin")
    def checkin(request: CheckinRequest):
        transaction_id = str(uuid.uuid4())
        with db_lock:
            pool = DistributedResourcePool(poolfile)
            transactions = load_transactions()
            for transaction in transactions:
                if transaction["id"] == request.transaction_id:
                    if transaction.get("checked_in") is not None:
                        raise HTTPException(
                            status_code=409,
                            detail=f"Transaction {request.transaction_id} already checked in",
                        )
                    try:
                        pool.checkin(transaction["target_host"], transaction["resources"])
                    except ValueError as e:
                        raise HTTPException(status_code=404, detail=str(e))
                    transaction["checked_in"] = datetime.datetime.now().isoformat()
                    pool.save()
                    save_transactions(transactions)
                    break
            else:
                raise HTTPException(status_code=404, detail="Transaction ID not found")
            return {
                "success": True,
                "message": "Resources returned to pool",
                "transaction_id": transaction_id,
            }

    @app.get("/status")
    def status():
        transaction_id = str(uuid.uuid4())
        with db_lock:
            pool = DistributedResourcePool(poolfile)
            return {"success": True, "database": pool.db, "transaction_id": transaction_id}

    @app.get("/health")
    def health():
        return {"success": True, "status": "ok"}

    @app.post("/add_host")
    def add_host(request: AddHostRequest):
        transaction_id = str(uuid.uuid4())
        with db_lock:
            pool = DistributedResourcePool(poolfile)
            try:
                pool.add(
                    host=request.hostname,
                    resources=request.resources,
                    tags=request.tags,
                    groups=request.groups,
                    state=request.state,
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            pool.save()
            return {
                "success": True,
                "message": f"Host {request.hostname} added to distributed resource pool",
                "transaction_id": transaction_id,
            }

    @app.post("/remove_host")
    def remove_host(hostname: str):
        transaction_id = str(uuid.uuid4())
        with db_lock:
            pool = DistributedResourcePool(poolfile)
            try:
                pool.pop(hostname)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e))
            pool.save()
            return {
                "success": True,
                "message": f"Removed {hostname} from the distributed resource pool",
                "transaction_id": transaction_id,
            }

    @app.post("/take_offline")
    def take_offline(hostname: str):
        transaction_id = str(uuid.uuid4())
        with db_lock:
            pool = DistributedResourcePool(poolfile)
            try:
                pool.take_offline(hostname)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e))
            pool.save()
            return {
                "success": True,
                "message": f"Took {hostname} offline",
                "transaction_id": transaction_id,
            }

    @app.post("/bring_online")
    def bring_online(hostname: str):
        transaction_id = str(uuid.uuid4())
        with db_lock:
            pool = DistributedResourcePool(poolfile)
            try:
                pool.bring_online(hostname)
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e))
            pool.save()
            return {
                "success": True,
                "message": f"Brought {hostname} online",
                "transaction_id": transaction_id,
            }

    @app.post("/restore_slots")
    def restore_slots():
        transaction_id = str(uuid.uuid4())
        with db_lock:
            pool = DistributedResourcePool(poolfile)
            pool.reset()
            pool.save()
            return {"success": True, "transaction_id": transaction_id}

    @app.post("/rx")
    def rx():
        transaction_id = str(uuid.uuid4())
        with db_lock:
            transactions = load_transactions()
            pool = DistributedResourcePool(poolfile)
            for transaction in transactions:
                if transaction["checked_in"]:
                    continue
                expires = datetime.datetime.fromisoformat(transaction["expires"])
                now = datetime.datetime.now()
                if now > expires:
                    pool.checkin(transaction["target_host"], transaction["resources"])
                    transaction["checked_in"] = now.isoformat()
            pool.save()
            save_transactions(transactions)
            return {"success": True, "transaction_id": transaction_id}

    @app.get("/ui_state")
    def ui_state():
        with db_lock:
            return build_ui_state()

    @app.post("/reset_db")
    def reset_db(request: ResetDBRequest):
        if request.confirm != "RESET":
            raise HTTPException(
                status_code=400,
                detail='Refusing to reset database unless confirm is exactly "RESET"',
            )

        transaction_id = str(uuid.uuid4())

        with db_lock:
            pool = DistributedResourcePool(poolfile)
            pool.db = {"machines": []}
            pool.save()
            save_transactions([])

        return {
            "success": True,
            "message": "Resource pool and transaction log reset",
            "transaction_id": transaction_id,
        }

    @app.get("/", response_class=HTMLResponse)
    def root_ui():
        return ui()

    @app.get("/ui", response_class=HTMLResponse)
    def ui():
        return HTMLResponse(
            """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Canary Distributed Resource Pool</title>
  <style>
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 2rem;
      background: #f7f7f8;
      color: #222;
    }
    h1, h2 {
      margin-bottom: 0.4rem;
    }
    .card {
      background: white;
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 1rem;
      margin: 1rem 0;
      box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    table {
      border-collapse: collapse;
      width: 100%;
      background: white;
    }
    th, td {
      border: 1px solid #ddd;
      padding: 0.45rem;
      text-align: left;
      vertical-align: top;
    }
    th {
      background: #eee;
    }
    code, pre {
      background: #f0f0f0;
      padding: 0.15rem 0.25rem;
      border-radius: 4px;
    }
    pre {
      white-space: pre-wrap;
      overflow-x: auto;
    }
    input, select, button {
      margin: 0.2rem;
      padding: 0.4rem;
    }
    button {
      cursor: pointer;
    }
    .danger {
      background: #b00020;
      color: white;
      border: 1px solid #7a0016;
      border-radius: 4px;
    }
    .warn {
      color: #9a6700;
      font-weight: 600;
    }
    .ok {
      color: #137333;
      font-weight: 600;
    }
    .offline {
      color: #b00020;
      font-weight: 600;
    }
    .muted {
      color: #666;
    }
    .row {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      align-items: center;
    }
    .grow {
      flex: 1;
      min-width: 15rem;
    }
  </style>
</head>
<body>
  <h1>Canary Distributed Resource Pool</h1>
  <p class="muted">
    Minimal administrative UI for local/container testing.
  </p>

  <div class="card">
    <h2>Actions</h2>
    <button onclick="refresh()">Refresh</button>
    <button onclick="restoreSlots()">Restore All Slots</button>
    <button class="danger" onclick="resetDb()">Reset DB</button>
    <span id="message" class="muted"></span>
  </div>

  <div class="card">
    <h2>Add Machine</h2>
    <div class="row">
      <input id="add-hostname" class="grow" placeholder="hostname, e.g. worker01">
      <input id="add-resources" class="grow" placeholder="resources, e.g. cpus=32,gpus=4">
      <input id="add-tags" class="grow" placeholder="tags, comma-separated">
      <input id="add-groups" class="grow" placeholder="groups, comma-separated">
      <select id="add-state">
        <option value="online">online</option>
        <option value="offline">offline</option>
      </select>
      <button onclick="addMachine()">Add</button>
    </div>
  </div>

  <div class="card">
    <h2>Machines</h2>
    <div id="machines"></div>
  </div>

  <div class="card">
    <h2>Active Checkouts</h2>
    <div id="transactions"></div>
  </div>

<script>
function setMessage(msg, isError=false) {
  const el = document.getElementById("message");
  el.textContent = msg || "";
  el.style.color = isError ? "#b00020" : "#137333";
}

function esc(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function splitComma(value) {
  return value
    .split(",")
    .map(x => x.trim())
    .filter(x => x.length > 0);
}

function parseResources(value) {
  const resources = [];
  const parts = value
    .split(/[ ,]+/)
    .map(x => x.trim())
    .filter(x => x.length > 0);

  for (const part of parts) {
    const m = part.match(/^([^=:]+)[=:](\\d+)$/);
    if (!m) {
      throw new Error("Invalid resource spec: " + part + ". Expected e.g. cpus=32");
    }
    resources.push({
      type: m[1],
      count: Number(m[2]),
    });
  }

  return resources;
}

async function api(path, options={}) {
  const response = await fetch(path, options);
  const text = await response.text();

  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }

  if (!response.ok) {
    const detail = data.detail || data.raw || response.statusText;
    throw new Error(detail);
  }

  return data;
}

function resourceSummaryHtml(summary) {
  const keys = Object.keys(summary || {}).sort();
  if (keys.length === 0) {
    return "<span class='muted'>none</span>";
  }

  return keys.map(rtype => {
    const item = summary[rtype];
    return (
      "<div><code>" + esc(rtype) + "</code>: " +
      "instances=" + esc(item.instances) + ", " +
      "free=" + esc(item.free) + ", " +
      "used=" + esc(item.used) +
      "</div>"
    );
  }).join("");
}

function resourcesJsonHtml(resources) {
  return "<pre>" + esc(JSON.stringify(resources || {}, null, 2)) + "</pre>";
}

function renderMachines(machines) {
  const container = document.getElementById("machines");

  if (!machines || machines.length === 0) {
    container.innerHTML = "<p class='muted'>No machines in database.</p>";
    return;
  }

  let html = "";
  html += "<table>";
  html += "<thead><tr>";
  html += "<th>Host</th>";
  html += "<th>State</th>";
  html += "<th>Tags</th>";
  html += "<th>Groups</th>";
  html += "<th>Resources</th>";
  html += "<th>Actions</th>";
  html += "</tr></thead><tbody>";

  for (const machine of machines) {
    const stateClass = machine.state === "online" ? "ok" : "offline";
    html += "<tr>";
    html += "<td><code>" + esc(machine.hostname) + "</code></td>";
    html += "<td class='" + stateClass + "'>" + esc(machine.state) + "</td>";
    html += "<td>" + esc((machine.tags || []).join(", ")) + "</td>";
    html += "<td>" + esc((machine.groups || []).join(", ")) + "</td>";
    html += "<td>" + resourceSummaryHtml(machine.resource_summary) + "</td>";
    html += "<td>";
    html += "<button onclick='takeOffline(" + JSON.stringify(machine.hostname) + ")'>Offline</button>";
    html += "<button onclick='bringOnline(" + JSON.stringify(machine.hostname) + ")'>Online</button>";
    html += "<button class='danger' onclick='removeMachine(" + JSON.stringify(machine.hostname) + ")'>Remove</button>";
    html += "</td>";
    html += "</tr>";
  }

  html += "</tbody></table>";
  container.innerHTML = html;
}

function renderTransactions(transactions) {
  const container = document.getElementById("transactions");

  if (!transactions || transactions.length === 0) {
    container.innerHTML = "<p class='muted'>No active checkouts.</p>";
    return;
  }

  let html = "";
  html += "<table>";
  html += "<thead><tr>";
  html += "<th>Transaction</th>";
  html += "<th>Target Host</th>";
  html += "<th>User</th>";
  html += "<th>Calling Host</th>";
  html += "<th>Checked Out</th>";
  html += "<th>Expires</th>";
  html += "<th>Resources</th>";
  html += "</tr></thead><tbody>";

  for (const tx of transactions) {
    html += "<tr>";
    html += "<td><code>" + esc(tx.id) + "</code>";
    if (tx.expired) {
      html += "<div class='warn'>expired</div>";
    }
    html += "</td>";
    html += "<td><code>" + esc(tx.target_host) + "</code></td>";
    html += "<td>" + esc(tx.user || "unknown") + "</td>";
    html += "<td>" + esc(tx.calling_host || "unknown") + "</td>";
    html += "<td>" + esc(tx.checked_out) + "</td>";
    html += "<td>" + esc(tx.expires) + "</td>";
    html += "<td>" + resourcesJsonHtml(tx.resources) + "</td>";
    html += "</tr>";
  }

  html += "</tbody></table>";
  container.innerHTML = html;
}

async function refresh() {
  try {
    const data = await api("/ui_state");
    renderMachines(data.machines);
    renderTransactions(data.active_transactions);
    setMessage("Refreshed.");
  } catch (err) {
    setMessage(String(err), true);
  }
}

async function addMachine() {
  try {
    const hostname = document.getElementById("add-hostname").value.trim();
    const resourcesText = document.getElementById("add-resources").value.trim();
    const tagsText = document.getElementById("add-tags").value.trim();
    const groupsText = document.getElementById("add-groups").value.trim();
    const state = document.getElementById("add-state").value;

    if (!hostname) {
      throw new Error("Hostname is required.");
    }
    if (!resourcesText) {
      throw new Error("Resources are required, e.g. cpus=32.");
    }

    const payload = {
      hostname: hostname,
      resources: parseResources(resourcesText),
      state: state,
    };

    const tags = splitComma(tagsText);
    const groups = splitComma(groupsText);

    if (tags.length > 0) payload.tags = tags;
    if (groups.length > 0) payload.groups = groups;

    await api("/add_host", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });

    document.getElementById("add-hostname").value = "";
    document.getElementById("add-resources").value = "";
    document.getElementById("add-tags").value = "";
    document.getElementById("add-groups").value = "";

    setMessage("Machine added.");
    await refresh();
  } catch (err) {
    setMessage(String(err), true);
  }
}

async function removeMachine(hostname) {
  try {
    if (!confirm("Remove machine " + hostname + "?")) return;

    await api("/remove_host?hostname=" + encodeURIComponent(hostname), {
      method: "POST",
    });

    setMessage("Machine removed.");
    await refresh();
  } catch (err) {
    setMessage(String(err), true);
  }
}

async function takeOffline(hostname) {
  try {
    await api("/take_offline?hostname=" + encodeURIComponent(hostname), {
      method: "POST",
    });
    setMessage("Machine taken offline.");
    await refresh();
  } catch (err) {
    setMessage(String(err), true);
  }
}

async function bringOnline(hostname) {
  try {
    await api("/bring_online?hostname=" + encodeURIComponent(hostname), {
      method: "POST",
    });
    setMessage("Machine brought online.");
    await refresh();
  } catch (err) {
    setMessage(String(err), true);
  }
}

async function restoreSlots() {
  try {
    if (!confirm("Restore all resource slots? This may invalidate active checkout accounting.")) return;

    await api("/restore_slots", {
      method: "POST",
    });

    setMessage("Slots restored.");
    await refresh();
  } catch (err) {
    setMessage(String(err), true);
  }
}

async function resetDb() {
  try {
    const value = prompt('This will delete all machines and transactions. Type RESET to continue.');
    if (value !== "RESET") {
      setMessage("Reset cancelled.");
      return;
    }

    await api("/reset_db", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({confirm: "RESET"}),
    });

    setMessage("Database reset.");
    await refresh();
  } catch (err) {
    setMessage(String(err), true);
  }
}

refresh();
setInterval(refresh, 10000);
</script>
</body>
</html>
            """
        )

    return app
