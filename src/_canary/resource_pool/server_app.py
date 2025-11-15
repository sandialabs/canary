import uuid
from typing import Any

from .rpool import ResourcePool
from .rpool import ResourceUnavailable


def create_pool_server_app_fastapi(pool: ResourcePool):
    """Build FastAPI app for local resource pool."""

    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="Canary Local Resource Pool")
    ledger: dict[str, Any] = {}

    @app.post("/accommodates")
    async def accommodates(request: list[dict[str, Any]]) -> JSONResponse:
        result = pool.accommodates(request)
        return JSONResponse(status_code=200, content={"ok": result.ok, "reason": result.reason})

    @app.post("/checkout")
    async def checkout(request: list[dict[str, Any]]) -> JSONResponse:
        transaction_id = str(uuid.uuid4())
        try:
            resources = pool.checkout(request)
        except ResourceUnavailable as e:
            return JSONResponse(status_code=404, content={"error": "ResourceUnavailable"})
        else:
            ledger[transaction_id] = resources
            return JSONResponse(
                status_code=200, content={"transaction_id": transaction_id, "resources": resources}
            )

    @app.post("/checkin")
    async def checkin(request: dict[str, list[dict]]) -> JSONResponse:
        # resources = ledger.get(trnsaction_id)
        # if not resources:
        #    return JSONResponse(status_code=400, content={"error": "resources ..."})
        pool.checkin(request)
        return JSONResponse(status_code=200, content={"status": "ok"})

    @app.get("/types")
    async def types() -> JSONResponse:
        return JSONResponse(status_code=200, content={"types": pool.types})

    @app.get("/types")
    async def count(type: str) -> JSONResponse:
        return JSONResponse(status_code=200, content={"count": pool.count(type)})

    @app.get("/status")
    async def status() -> JSONResponse:
        return JSONResponse(status_code=200, content={"status": "ok"})

    return app


def create_pool_server_app_starlette(pool: ResourcePool):
    """
    Create a Starlette app exposing the resource pool API.

    Parameters
    ----------
    resource_pool : dict
        Shared resource pool managed by the main process.
    """
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    ledger: dict[str, Any] = {}

    # --- Route Handlers ---
    async def accommodates(request):
        req = await request.json()
        result = pool.accommodates(req)
        return JSONResponse(status_code=200, content={"ok": result.ok, "reason": result.reason})

    async def checkout(request):
        resource_groups = await request.json()
        transaction_id = str(uuid.uuid4())
        try:
            resources = pool.checkout(resource_groups)
        except ResourceUnavailable as e:
            return JSONResponse(status_code=404, content={"error": "ResourceUnavailable"})
        else:
            ledger[transaction_id] = resources
            return JSONResponse(
                status_code=200, content={"transaction_id": transaction_id, "resources": resources}
            )

    async def checkin(request):
        resources = await request.json()
        pool.checkin(resources)
        return JSONResponse(status_code=200, content={"status": "ok"})

    async def count(request):
        type = await request.json()
        return JSONResponse(status_code=200, content={"count": pool.count(type)})

    async def types(request):
        return JSONResponse(status_code=200, content={"types": pool.types})

    async def status(request):
        return JSONResponse(status_code=200, content={"status": "ok"})

    # --- Assemble app ---
    routes = [
        Route("/status", status, methods=["GET"]),
        Route("/accommodates", accommodates, methods=["POST"]),
        Route("/checkout", checkout, methods=["POST"]),
        Route("/checkin", checkin, methods=["POST"]),
        Route("/count", count, methods=["POST"]),
        Route("/types", types, methods=["GET"]),
    ]

    app = Starlette(debug=False, routes=routes)
    return app
