# k8s-observability-lab

Kubernetes × マイクロサービス × Observability (OpenTelemetry) を実地で学ぶためのサンプルプロジェクト。

```
[client] → gateway (Python/FastAPI) → order (Python/FastAPI) → inventory (Rust/axum)
                │                        │                        │
                └────────── OTLP ────────┴──────── OTLP ──────────┘
                                    ↓
                            OpenTelemetry Collector
                                    ↓
                 Grafana LGTM (ローカル) / Datadog / New Relic
```

3つのマイクロサービス (Python 2つ + Rust 1つ) が分散トレースで繋がり、
トレース・メトリクス・ログの「3本柱」を OpenTelemetry で統一的に収集します。

## 学習パス (推奨順)

| Step | 環境 | 所要目安 | ドキュメント |
|------|------|---------|-------------|
| 1 | docker compose | 半日 | このREADME |
| 2 | kind (ローカルk8s) | 1〜2日 | このREADME + [docs/architecture.md](docs/architecture.md) |
| 3 | EKS | 2〜3日 | [docs/eks-migration.md](docs/eks-migration.md) |
| 4 | Datadog / New Relic 接続 | 各半日 | [docs/observability.md](docs/observability.md) |

全体の学習ロードマップ (2019年の知識からのアップデート事項含む) は
[docs/roadmap.md](docs/roadmap.md) を参照。

## Step 1: docker compose で動かす

```bash
cd deploy/compose
docker compose up --build -d

# 動作確認
curl http://localhost:8080/api/products
curl -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"product_id": 1, "quantity": 2}'

# 負荷をかけてテレメトリを生成
pip install httpx
python ../../scripts/loadgen.py
```

Grafana を http://localhost:3000 で開き:

1. **Explore → Tempo**: トレースを検索。gateway → order → inventory と
   3サービス・2言語をまたぐスパンツリーが見える
2. **Explore → Prometheus**: `orders_created_total` などのカスタムメトリクス
3. **Explore → Loki**: ログ。`trace_id` からトレースへジャンプできる

### 観察してほしい「わざと仕込んだ異常」

- `{"product_id": 99}` を注文 → inventory 内の `slow_backend_lookup` スパンが
  1.5秒を占めるのがトレースで一目瞭然
- `{"product_id": 999}` を注文 → 500 エラー。エラートレースがどう記録されるか観察
- `{"product_id": 3}` を大量注文 → 在庫切れ (409)。`orders_created_total{result="out_of_stock"}` が増える

## Step 2: kind (ローカル Kubernetes) で動かす

```bash
# クラスタ作成
kind create cluster --name obs-lab

# イメージをビルドして kind に読み込む
docker build -t obs-lab/gateway:dev services/gateway
docker build -t obs-lab/order:dev services/order
docker build -t obs-lab/inventory:dev services/inventory
kind load docker-image obs-lab/gateway:dev obs-lab/order:dev obs-lab/inventory:dev --name obs-lab

# デプロイ
kubectl apply -k deploy/k8s/overlays/local-kind

# 動作確認
kubectl -n obs-lab get pods
kubectl -n obs-lab port-forward svc/gateway 8080:8000 &
kubectl -n obs-lab port-forward svc/lgtm 3000:3000 &
curl http://localhost:8080/api/products
```

compose と同じアプリ・同じ Collector 設定が、そのまま k8s に載ることを確認してください。
kustomize の base/overlay 構造 (deploy/k8s/) が「環境差分の管理」の実例です。

## Step 3: EKS へ

[docs/eks-migration.md](docs/eks-migration.md) の手順で、
同じマニフェスト (overlays/eks) を EKS にデプロイします。

## ディレクトリ構成

```
services/
  gateway/    FastAPI: 公開API (BFF)
  order/      FastAPI: 注文処理 + カスタムメトリクス
  inventory/  Rust(axum): 在庫管理 + 意図的な遅延/エラー
deploy/
  compose/    docker compose 一式 (Collector設定含む)
  k8s/
    base/               全環境共通のマニフェスト
    overlays/local-kind kind用 (LGTM同居)
    overlays/eks        EKS用 (ECRイメージ, SaaS exporter, RBAC)
docs/         解説ドキュメント
scripts/      負荷生成スクリプト
```
