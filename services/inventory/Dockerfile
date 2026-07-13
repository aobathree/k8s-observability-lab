# --- ビルドステージ ---
FROM rust:1.95-slim AS builder
WORKDIR /build

# 依存関係だけ先にビルドしてレイヤーキャッシュを効かせる
COPY Cargo.toml Cargo.lock* ./
RUN mkdir src && echo "fn main() {}" > src/main.rs \
    && cargo build --release \
    && rm -rf src

COPY src ./src
# ダミー main.rs のキャッシュを無効化して本体をビルド
RUN touch src/main.rs && cargo build --release

# --- 実行ステージ (最小イメージ) ---
FROM gcr.io/distroless/cc-debian12:nonroot
COPY --from=builder /build/target/release/inventory /usr/local/bin/inventory
EXPOSE 8001
ENTRYPOINT ["/usr/local/bin/inventory"]
