"""order サービス: 注文の受付と管理。

在庫の引き当てを inventory サービス (Rust) に依頼する。
カスタムメトリクス (orders_created カウンター、処理時間ヒストグラム) を
発行し、Observability 学習の題材とする。
"""

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from opentelemetry import metrics, trace
from pydantic import BaseModel, Field

from .otel import setup_otel

INVENTORY_URL = os.environ.get("INVENTORY_URL", "http://inventory:8001")

logger = logging.getLogger("order")
tracer = trace.get_tracer("order")
meter = metrics.get_meter("order")

# インメモリの注文ストア (学習用。実運用では PostgreSQL / DynamoDB 等)
ORDERS: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=10.0)
    yield
    await app.state.http.aclose()


app = FastAPI(title="order", lifespan=lifespan)
setup_otel(app)

# --- カスタムメトリクス ---
orders_created = meter.create_counter(
    "orders_created",
    unit="{order}",
    description="作成された注文の数",
)
order_duration = meter.create_histogram(
    "order_processing_duration",
    unit="s",
    description="注文処理にかかった時間",
)


class OrderRequest(BaseModel):
    product_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=100)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/orders", status_code=201)
async def create_order(req: OrderRequest):
    start = time.monotonic()
    span = trace.get_current_span()
    span.set_attribute("app.product_id", req.product_id)

    # 在庫引き当て (Rust サービスへの HTTP 呼び出し。トレースは自動伝播)
    resp = await app.state.http.post(
        f"{INVENTORY_URL}/reserve",
        json={"product_id": req.product_id, "quantity": req.quantity},
    )
    if resp.status_code == 404:
        orders_created.add(1, {"result": "not_found"})
        raise HTTPException(status_code=404, detail="product not found")
    if resp.status_code == 409:
        # 在庫不足: メトリクスとログにも失敗として記録する
        orders_created.add(1, {"result": "out_of_stock"})
        logger.warning("out of stock: product_id=%s", req.product_id)
        raise HTTPException(status_code=409, detail="out of stock")
    resp.raise_for_status()

    order_id = str(uuid.uuid4())
    ORDERS[order_id] = {
        "order_id": order_id,
        "product_id": req.product_id,
        "quantity": req.quantity,
        "status": "confirmed",
    }

    elapsed = time.monotonic() - start
    orders_created.add(1, {"result": "success"})
    order_duration.record(elapsed)
    logger.info("order %s confirmed in %.3fs", order_id, elapsed)
    return ORDERS[order_id]


@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    order = ORDERS.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return order
