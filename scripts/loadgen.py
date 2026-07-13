#!/usr/bin/env python3
"""簡易負荷生成スクリプト。

トレース・メトリクス・ログを観察するためのトラフィックを作る。
通常注文に混ぜて、たまに「遅い商品(99)」「壊れる商品(999)」を注文し、
ダッシュボード上で異常が見えるようにする。

使い方:
    pip install httpx
    python scripts/loadgen.py [--url http://localhost:8080] [--rps 2]
"""

import argparse
import asyncio
import random
import sys

import httpx

WEIGHTED_PRODUCTS = [1, 1, 1, 2, 2, 3, 99, 999]  # 99/999 は少なめに混ぜる


async def one_request(client: httpx.AsyncClient, url: str) -> None:
    try:
        if random.random() < 0.3:
            r = await client.get(f"{url}/api/products")
            print(f"GET /api/products -> {r.status_code}")
        else:
            product_id = random.choice(WEIGHTED_PRODUCTS)
            r = await client.post(
                f"{url}/api/orders",
                json={"product_id": product_id, "quantity": random.randint(1, 3)},
            )
            print(f"POST /api/orders (product {product_id}) -> {r.status_code}")
    except httpx.HTTPError as e:
        print(f"request failed: {e}", file=sys.stderr)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--rps", type=float, default=2.0, help="1秒あたりのリクエスト数")
    args = parser.parse_args()

    async with httpx.AsyncClient(timeout=15.0) as client:
        print(f"generating ~{args.rps} req/s against {args.url} (Ctrl-C で停止)")
        while True:
            asyncio.ensure_future(one_request(client, args.url))
            await asyncio.sleep(1.0 / args.rps)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
