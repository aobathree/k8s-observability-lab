"""gateway サービス: 外部公開 API (BFF 的役割)。

order / inventory サービスへのリクエストを仲介する。
分散トレースは gateway → order → inventory と伝播する
(traceparent ヘッダーが httpx 計装により自動で付与される)。
"""

import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from pydantic import BaseModel, Field

from .otel import setup_otel

ORDER_URL = os.environ.get("ORDER_URL", "http://order:8000")
INVENTORY_URL = os.environ.get("INVENTORY_URL", "http://inventory:8001")

logger = logging.getLogger("gateway")
tracer = trace.get_tracer("gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=10.0)
    yield
    await app.state.http.aclose()


app = FastAPI(title="gateway", lifespan=lifespan)
setup_otel(app)


class OrderRequest(BaseModel):
    product_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=100)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/api/products")
async def list_products():
    """商品一覧を inventory (Rust) から取得する。"""
    resp = await app.state.http.get(f"{INVENTORY_URL}/products")
    resp.raise_for_status()
    return resp.json()


@app.post("/api/orders", status_code=201)
async def create_order(req: OrderRequest):
    """注文を order サービスへ転送する。"""
    # 手動スパンの例: 自動計装に加えて業務的な区切りを記録する
    with tracer.start_as_current_span("gateway.create_order") as span:
        span.set_attribute("app.product_id", req.product_id)
        span.set_attribute("app.quantity", req.quantity)
        resp = await app.state.http.post(f"{ORDER_URL}/orders", json=req.model_dump())
        if resp.status_code >= 400:
            logger.warning("order service returned %s: %s", resp.status_code, resp.text)
            raise HTTPException(status_code=resp.status_code, detail=resp.json().get("detail"))
        logger.info("order created for product_id=%s", req.product_id)
        return resp.json()


@app.get("/api/orders/{order_id}")
async def get_order(order_id: str):
    resp = await app.state.http.get(f"{ORDER_URL}/orders/{order_id}")
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="order not found")
    resp.raise_for_status()
    return resp.json()
