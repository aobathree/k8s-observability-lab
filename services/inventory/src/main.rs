//! inventory サービス: 在庫管理 (Rust / axum)。
//!
//! Python サービスからの traceparent ヘッダーを受け取り、
//! 同じ分散トレースの一部としてスパンを記録する。
//!
//! 学習用の「わざと遅い / わざと失敗する」商品を用意している:
//!   - product_id = 99  : 引き当てに 1.5 秒かかる (レイテンシ調査の練習)
//!   - product_id = 999 : 常に 500 エラー (エラートレース調査の練習)

use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use axum::{
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use axum_tracing_opentelemetry::middleware::{OtelAxumLayer, OtelInResponseLayer};
use serde::{Deserialize, Serialize};
use tracing::{info, instrument, warn};

#[derive(Clone, Serialize)]
struct Product {
    id: u32,
    name: String,
    stock: u32,
}

#[derive(Deserialize)]
struct ReserveRequest {
    product_id: u32,
    quantity: u32,
}

#[derive(Serialize)]
struct ReserveResponse {
    product_id: u32,
    reserved: u32,
    remaining: u32,
}

type Store = Arc<Mutex<HashMap<u32, Product>>>;

fn initial_stock() -> HashMap<u32, Product> {
    let items = [
        (1, "Kubernetes 完全ガイド", 50),
        (2, "マイクロサービスパターン", 30),
        (3, "オブザーバビリティ・エンジニアリング", 20),
        (99, "遅延デモ商品 (1.5秒かかる)", 100),
        (999, "エラーデモ商品 (常に失敗)", 100),
    ];
    items
        .into_iter()
        .map(|(id, name, stock)| {
            (
                id,
                Product {
                    id,
                    name: name.to_string(),
                    stock,
                },
            )
        })
        .collect()
}

async fn healthz() -> impl IntoResponse {
    Json(serde_json::json!({"status": "ok"}))
}

#[instrument(skip(store))]
async fn list_products(State(store): State<Store>) -> impl IntoResponse {
    let mut products: Vec<Product> = store.lock().unwrap().values().cloned().collect();
    products.sort_by_key(|p| p.id);
    info!(count = products.len(), "listing products");
    Json(products)
}

#[instrument(skip(store, req), fields(product_id = req.product_id, quantity = req.quantity))]
async fn reserve(
    State(store): State<Store>,
    Json(req): Json<ReserveRequest>,
) -> Result<Json<ReserveResponse>, (StatusCode, Json<serde_json::Value>)> {
    // デモ用: product_id=999 は常に内部エラー
    if req.product_id == 999 {
        warn!("simulated internal error triggered");
        return Err((
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(serde_json::json!({"detail": "simulated inventory backend failure"})),
        ));
    }

    // デモ用: product_id=99 は遅いバックエンドをシミュレート
    if req.product_id == 99 {
        slow_backend_lookup().await;
    }

    let mut store = store.lock().unwrap();
    let product = store.get_mut(&req.product_id).ok_or((
        StatusCode::NOT_FOUND,
        Json(serde_json::json!({"detail": "product not found"})),
    ))?;

    if product.stock < req.quantity {
        warn!(stock = product.stock, "insufficient stock");
        return Err((
            StatusCode::CONFLICT,
            Json(serde_json::json!({"detail": "out of stock"})),
        ));
    }

    product.stock -= req.quantity;
    info!(remaining = product.stock, "reserved stock");
    Ok(Json(ReserveResponse {
        product_id: req.product_id,
        reserved: req.quantity,
        remaining: product.stock,
    }))
}

/// 遅いバックエンド (レガシー DB 等) の呼び出しを模した子スパン。
/// トレース上で「どこで時間がかかっているか」が一目で分かる。
#[instrument]
async fn slow_backend_lookup() {
    tokio::time::sleep(Duration::from_millis(1500)).await;
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    // OTEL_EXPORTER_OTLP_ENDPOINT / OTEL_SERVICE_NAME を読んで
    // トレーサーと tracing サブスクライバーを初期化する
    let _guard = init_tracing_opentelemetry::config::TracingConfig::production().init_subscriber()?;

    let store: Store = Arc::new(Mutex::new(initial_stock()));

    let app = Router::new()
        .route("/products", get(list_products))
        .route("/reserve", post(reserve))
        // レスポンスヘッダーに trace_id を入れる (デバッグに便利)
        .layer(OtelInResponseLayer)
        // 受信リクエストごとにスパンを開始し、traceparent を取り込む
        .layer(OtelAxumLayer::default())
        // ヘルスチェックはトレース対象外にするため、レイヤーの外に置く
        .route("/healthz", get(healthz))
        .with_state(store);

    let addr = std::env::var("LISTEN_ADDR").unwrap_or_else(|_| "0.0.0.0:8001".to_string());
    let listener = tokio::net::TcpListener::bind(&addr).await?;
    info!(%addr, "inventory service listening");
    axum::serve(listener, app).await?;
    Ok(())
}
