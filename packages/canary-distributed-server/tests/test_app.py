# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""HTTP API tests for the FastAPI application.

Uses TestClient (httpx + starlette in-process) so no real server is started.
Each test gets a fresh temp directory for state isolation.
"""

import datetime
import json

import pytest
from fastapi.testclient import TestClient

from canary_distributed_server.app import make_fastapi

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def state_dir(tmp_path):
    """Isolated state directory for each test."""
    return tmp_path


@pytest.fixture()
def client(state_dir):
    """TestClient bound to a fresh app instance."""
    app = make_fastapi(state_dir)
    return TestClient(app)


@pytest.fixture()
def client_with_worker(state_dir):
    """TestClient with one 4-CPU worker machine pre-added."""
    app = make_fastapi(state_dir)
    c = TestClient(app)
    resp = c.post(
        "/add_host", json={"hostname": "worker01", "resources": [{"type": "cpus", "count": 4}]}
    )
    assert resp.status_code == 200
    return c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def checkout(client, cpus=1, timeout=300, tags=None, groups=None):
    payload = {
        "resources": [{"type": "cpus", "slots": 1} for _ in range(cpus)],
        "timeout": timeout,
    }
    if tags:
        payload["tags"] = tags
    if groups:
        payload["groups"] = groups
    return client.post("/checkout", json=payload)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# add_host / remove_host
# ---------------------------------------------------------------------------


class TestAddHost:
    def test_add_host_success(self, client):
        resp = client.post(
            "/add_host", json={"hostname": "worker01", "resources": [{"type": "cpus", "count": 4}]}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "worker01" in data["message"]

    def test_add_host_no_cpus_fails(self, client):
        resp = client.post(
            "/add_host", json={"hostname": "worker01", "resources": [{"type": "gpus", "count": 2}]}
        )
        assert resp.status_code == 400

    def test_add_duplicate_host_fails(self, client_with_worker):
        resp = client_with_worker.post(
            "/add_host", json={"hostname": "worker01", "resources": [{"type": "cpus", "count": 4}]}
        )
        assert resp.status_code == 400

    def test_add_host_with_tags_and_groups(self, client):
        resp = client.post(
            "/add_host",
            json={
                "hostname": "worker01",
                "resources": [{"type": "cpus", "count": 4}],
                "tags": ["gpu"],
                "groups": ["teamA"],
            },
        )
        assert resp.status_code == 200

    def test_add_host_with_gpus(self, client):
        resp = client.post(
            "/add_host",
            json={
                "hostname": "worker01",
                "resources": [{"type": "cpus", "count": 4}, {"type": "gpus", "count": 2}],
            },
        )
        assert resp.status_code == 200
        # Verify via status
        status = client.get("/status").json()
        m = status["database"]["machines"][0]
        assert "gpus" in m["resources"]
        assert len(m["resources"]["gpus"]) == 2


class TestRemoveHost:
    def test_remove_host_success(self, client_with_worker):
        resp = client_with_worker.post("/remove_host", params={"hostname": "worker01"})
        assert resp.status_code == 200
        status = client_with_worker.get("/status").json()
        assert status["database"]["machines"] == []

    def test_remove_missing_host(self, client):
        resp = client.post("/remove_host", params={"hostname": "nonexistent"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_empty_pool(self, client):
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["database"]["machines"] == []

    def test_status_shows_machines(self, client_with_worker):
        resp = client_with_worker.get("/status")
        assert resp.status_code == 200
        machines = resp.json()["database"]["machines"]
        assert len(machines) == 1
        assert machines[0]["hostname"] == "worker01"


# ---------------------------------------------------------------------------
# Take offline / bring online
# ---------------------------------------------------------------------------


class TestOnlineOffline:
    def test_take_offline(self, client_with_worker):
        resp = client_with_worker.post("/take_offline", params={"hostname": "worker01"})
        assert resp.status_code == 200
        status = client_with_worker.get("/status").json()
        assert status["database"]["machines"][0]["state"] == "offline"

    def test_bring_online(self, client_with_worker):
        client_with_worker.post("/take_offline", params={"hostname": "worker01"})
        resp = client_with_worker.post("/bring_online", params={"hostname": "worker01"})
        assert resp.status_code == 200
        status = client_with_worker.get("/status").json()
        assert status["database"]["machines"][0]["state"] == "online"

    def test_take_offline_missing_host(self, client):
        resp = client.post("/take_offline", params={"hostname": "ghost"})
        assert resp.status_code == 404

    def test_bring_online_missing_host(self, client):
        resp = client.post("/bring_online", params={"hostname": "ghost"})
        assert resp.status_code == 404

    def test_offline_machine_cannot_be_checked_out(self, client_with_worker):
        client_with_worker.post("/take_offline", params={"hostname": "worker01"})
        resp = checkout(client_with_worker, cpus=1)
        assert resp.status_code == 200
        assert resp.json()["success"] is False


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------


class TestCheckout:
    def test_checkout_success(self, client_with_worker):
        resp = checkout(client_with_worker, cpus=1)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["hostname"] == "worker01"
        assert "transaction_id" in data
        assert "cpus" in data["resources"]

    def test_checkout_depletes_pool(self, client_with_worker):
        for _ in range(4):
            resp = checkout(client_with_worker, cpus=1)
            assert resp.json()["success"] is True
        resp = checkout(client_with_worker, cpus=1)
        assert resp.json()["success"] is False

    def test_checkout_empty_pool(self, client):
        resp = checkout(client, cpus=1)
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_checkout_records_transaction(self, client_with_worker, state_dir):
        resp = checkout(client_with_worker, cpus=1)
        transaction_id = resp.json()["transaction_id"]
        txfile = state_dir / "transactions.jsons"
        assert txfile.exists()
        txns = [json.loads(line) for line in txfile.read_text().splitlines() if line.strip()]
        ids = [t["id"] for t in txns]
        assert transaction_id in ids

    def test_checkout_transaction_has_expiry(self, client_with_worker, state_dir):
        checkout(client_with_worker, cpus=1, timeout=600)
        txfile = state_dir / "transactions.jsons"
        txns = [json.loads(line) for line in txfile.read_text().splitlines() if line.strip()]
        assert txns[0]["expires"] is not None
        # Expiry should be ~600s from now
        expires = datetime.datetime.fromisoformat(txns[0]["expires"])
        checked_out = datetime.datetime.fromisoformat(txns[0]["checked_out"])
        delta = (expires - checked_out).total_seconds()
        assert 595 < delta < 605

    def test_checkout_with_tag_filter(self, client):
        client.post(
            "/add_host",
            json={
                "hostname": "gpu-node",
                "resources": [{"type": "cpus", "count": 4}],
                "tags": ["gpu"],
            },
        )
        client.post(
            "/add_host", json={"hostname": "cpu-node", "resources": [{"type": "cpus", "count": 4}]}
        )
        resp = checkout(client, cpus=1, tags=["gpu"])
        assert resp.json()["hostname"] == "gpu-node"

    def test_checkout_stores_user_and_calling_host_headers(self, client_with_worker, state_dir):
        checkout(client_with_worker, cpus=1)
        # Re-issue with explicit headers
        resp = client_with_worker.post(
            "/checkout",
            json={"resources": [{"type": "cpus", "slots": 1}], "timeout": 300},
            headers={"X-User": "alice", "X-Host": "submit-node"},
        )
        data = resp.json()
        txfile = state_dir / "transactions.jsons"
        txns = [json.loads(line) for line in txfile.read_text().splitlines() if line.strip()]
        tx = next(t for t in txns if t["id"] == data["transaction_id"])
        assert tx["user"] == "alice"
        assert tx["calling_host"] == "submit-node"


# ---------------------------------------------------------------------------
# Checkin
# ---------------------------------------------------------------------------


class TestCheckin:
    def test_checkin_success(self, client_with_worker):
        tx_id = checkout(client_with_worker, cpus=1).json()["transaction_id"]
        resp = client_with_worker.post("/checkin", json={"transaction_id": tx_id})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_checkin_restores_slots(self, client_with_worker):
        # Exhaust pool, check in one, then checkout should succeed again
        txns = []
        for _ in range(4):
            txns.append(checkout(client_with_worker, cpus=1).json()["transaction_id"])
        # Pool should be empty now
        assert checkout(client_with_worker, cpus=1).json()["success"] is False
        # Check in one
        client_with_worker.post("/checkin", json={"transaction_id": txns[0]})
        # Now checkout should succeed
        resp = checkout(client_with_worker, cpus=1)
        assert resp.json()["success"] is True

    def test_checkin_missing_transaction(self, client_with_worker):
        resp = client_with_worker.post("/checkin", json={"transaction_id": "nonexistent-uuid"})
        assert resp.status_code == 404

    def test_checkin_double_checkin_rejected(self, client_with_worker):
        """Checking in the same transaction twice must be rejected (409)."""
        tx_id = checkout(client_with_worker, cpus=1).json()["transaction_id"]
        r1 = client_with_worker.post("/checkin", json={"transaction_id": tx_id})
        assert r1.status_code == 200
        r2 = client_with_worker.post("/checkin", json={"transaction_id": tx_id})
        assert r2.status_code == 409

    def test_checkin_double_checkin_does_not_overshoot_slots(self, client_with_worker):
        """Even if second checkin is attempted, pool slots must not exceed original count."""
        tx_id = checkout(client_with_worker, cpus=1).json()["transaction_id"]
        client_with_worker.post("/checkin", json={"transaction_id": tx_id})
        # Second checkin — expect 409
        client_with_worker.post("/checkin", json={"transaction_id": tx_id})
        # Pool should still have exactly 4 CPUs (original)
        status = client_with_worker.get("/status").json()
        m = status["database"]["machines"][0]
        free = sum(inst["slots"] for inst in m["resources"]["cpus"])
        assert free == 4


# ---------------------------------------------------------------------------
# Accommodates
# ---------------------------------------------------------------------------


class TestAccommodates:
    def test_accommodates_available(self, client_with_worker):
        resp = client_with_worker.post(
            "/accommodates", json={"resources": [{"type": "cpus", "slots": 1}]}
        )
        assert resp.status_code == 200
        assert resp.json()["accommodates"] is True

    def test_accommodates_empty_pool(self, client):
        resp = client.post("/accommodates", json={"resources": [{"type": "cpus", "slots": 1}]})
        assert resp.status_code == 200
        assert resp.json()["accommodates"] is False

    def test_accommodates_after_full_checkout(self, client_with_worker):
        """accommodates must reflect live pool state, not static initial counts."""
        for _ in range(4):
            checkout(client_with_worker, cpus=1)
        resp = client_with_worker.post(
            "/accommodates", json={"resources": [{"type": "cpus", "slots": 1}]}
        )
        assert resp.json()["accommodates"] is False

    def test_accommodates_offline_machine_not_counted(self, client_with_worker):
        client_with_worker.post("/take_offline", params={"hostname": "worker01"})
        resp = client_with_worker.post(
            "/accommodates", json={"resources": [{"type": "cpus", "slots": 1}]}
        )
        assert resp.json()["accommodates"] is False


# ---------------------------------------------------------------------------
# RX (expire and reclaim)
# ---------------------------------------------------------------------------


class TestRX:
    def test_rx_does_not_affect_active_transactions(self, client_with_worker):
        """rx() must not touch transactions that haven't expired."""
        checkout(client_with_worker, cpus=1, timeout=3600)
        resp = client_with_worker.post("/rx")
        assert resp.status_code == 200
        # Pool should still show the slot as checked out
        status = client_with_worker.get("/status").json()
        m = status["database"]["machines"][0]
        free = sum(inst["slots"] for inst in m["resources"]["cpus"])
        assert free == 3  # 4 total - 1 checked out

    def test_rx_reclaims_expired_transactions(self, client_with_worker, state_dir):
        """rx() must return slots for transactions whose expiry has passed."""
        checkout(client_with_worker, cpus=1, timeout=1)
        # Manually backdate the expiry in the transactions file
        txfile = state_dir / "transactions.jsons"
        txns = [json.loads(l) for l in txfile.read_text().splitlines() if l.strip()]
        past = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat()
        txns[0]["expires"] = past
        with txfile.open("w") as f:
            for t in txns:
                f.write(json.dumps(t) + "\n")

        resp = client_with_worker.post("/rx")
        assert resp.status_code == 200

        # Pool should be fully restored
        status = client_with_worker.get("/status").json()
        m = status["database"]["machines"][0]
        free = sum(inst["slots"] for inst in m["resources"]["cpus"])
        assert free == 4


# ---------------------------------------------------------------------------
# Restore slots
# ---------------------------------------------------------------------------


class TestRestoreSlots:
    def test_restore_slots(self, client_with_worker):
        checkout(client_with_worker, cpus=2)
        resp = client_with_worker.post("/restore_slots")
        assert resp.status_code == 200
        status = client_with_worker.get("/status").json()
        m = status["database"]["machines"][0]
        free = sum(inst["slots"] for inst in m["resources"]["cpus"])
        assert free == 4


# ---------------------------------------------------------------------------
# Reset DB
# ---------------------------------------------------------------------------


class TestResetDB:
    def test_reset_requires_confirm(self, client_with_worker):
        resp = client_with_worker.post("/reset_db", json={"confirm": "yes"})
        assert resp.status_code == 400

    def test_reset_clears_machines(self, client_with_worker):
        resp = client_with_worker.post("/reset_db", json={"confirm": "RESET"})
        assert resp.status_code == 200
        status = client_with_worker.get("/status").json()
        assert status["database"]["machines"] == []

    def test_reset_clears_transactions(self, client_with_worker, state_dir):
        checkout(client_with_worker, cpus=1)
        client_with_worker.post("/reset_db", json={"confirm": "RESET"})
        txfile = state_dir / "transactions.jsons"
        content = txfile.read_text().strip()
        assert content == ""


# ---------------------------------------------------------------------------
# UI endpoints
# ---------------------------------------------------------------------------


class TestUI:
    def test_ui_state_returns_machines(self, client_with_worker):
        resp = client_with_worker.get("/ui_state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["machines"]) == 1
        assert data["machines"][0]["hostname"] == "worker01"

    def test_ui_state_resource_summary(self, client_with_worker):
        resp = client_with_worker.get("/ui_state")
        summary = resp.json()["machines"][0]["resource_summary"]
        assert "cpus" in summary
        assert summary["cpus"]["instances"] == 4
        assert summary["cpus"]["free"] == 4
        assert summary["cpus"]["used"] == 0

    def test_ui_state_shows_active_checkout(self, client_with_worker):
        checkout(client_with_worker, cpus=1)
        resp = client_with_worker.get("/ui_state")
        active = resp.json()["active_transactions"]
        assert len(active) == 1
        assert active[0]["target_host"] == "worker01"

    def test_ui_state_checkout_reduces_free(self, client_with_worker):
        checkout(client_with_worker, cpus=2)
        summary = client_with_worker.get("/ui_state").json()["machines"][0]["resource_summary"]
        assert summary["cpus"]["free"] == 2
        assert summary["cpus"]["used"] == 2

    def test_root_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_ui_returns_html(self, client):
        resp = client.get("/ui")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# Persistence: state survives app restart
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_pool_persists_across_app_restart(self, state_dir):
        app1 = make_fastapi(state_dir)
        c1 = TestClient(app1)
        c1.post(
            "/add_host", json={"hostname": "worker01", "resources": [{"type": "cpus", "count": 4}]}
        )

        # New app instance, same state dir
        app2 = make_fastapi(state_dir)
        c2 = TestClient(app2)
        status = c2.get("/status").json()
        assert len(status["database"]["machines"]) == 1
        assert status["database"]["machines"][0]["hostname"] == "worker01"

    def test_transactions_persist_across_restart(self, state_dir):
        app1 = make_fastapi(state_dir)
        c1 = TestClient(app1)
        c1.post(
            "/add_host", json={"hostname": "worker01", "resources": [{"type": "cpus", "count": 4}]}
        )
        tx_id = c1.post(
            "/checkout", json={"resources": [{"type": "cpus", "slots": 1}], "timeout": 300}
        ).json()["transaction_id"]

        # New app instance
        app2 = make_fastapi(state_dir)
        c2 = TestClient(app2)
        # Check in via new instance — should succeed
        resp = c2.post("/checkin", json={"transaction_id": tx_id})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Multi-machine scenarios
# ---------------------------------------------------------------------------


class TestMultiMachine:
    def test_checkout_picks_machine_with_most_capacity(self, client):
        client.post(
            "/add_host", json={"hostname": "small", "resources": [{"type": "cpus", "count": 4}]}
        )
        client.post(
            "/add_host", json={"hostname": "large", "resources": [{"type": "cpus", "count": 16}]}
        )
        # Requesting 2 CPUs — large has more capacity, should be picked
        resp = checkout(client, cpus=2)
        assert resp.json()["hostname"] == "large"

    def test_checkout_falls_back_to_second_machine(self, client):
        client.post(
            "/add_host", json={"hostname": "worker01", "resources": [{"type": "cpus", "count": 1}]}
        )
        client.post(
            "/add_host", json={"hostname": "worker02", "resources": [{"type": "cpus", "count": 4}]}
        )
        # First checkout lands on worker02 (more capacity)
        checkout(client, cpus=1)
        # Exhaust worker02's advantage via repeated checkout or test directly
        # Exhaust worker01 as well
        # More straightforward: checkout enough to force fallback
        for _ in range(4):
            checkout(client, cpus=1)
        # Both should have no CPUs left
        resp = checkout(client, cpus=1)
        assert resp.json()["success"] is False

    def test_checkout_with_group_restricts_to_group(self, client):
        client.post(
            "/add_host",
            json={
                "hostname": "shared",
                "resources": [{"type": "cpus", "count": 4}],
                "groups": ["teamA", "teamB"],
            },
        )
        client.post(
            "/add_host",
            json={
                "hostname": "private",
                "resources": [{"type": "cpus", "count": 4}],
                "groups": ["teamA"],
            },
        )
        # teamB can only use 'shared'
        resp = checkout(client, cpus=1, groups=["teamB"])
        assert resp.json()["hostname"] == "shared"
