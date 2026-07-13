# Observability 解説 — OpenTelemetry を軸に

## 3本柱と、それを繋ぐもの

| 柱 | 問いに答える | このプロジェクトでの実物 |
|----|-------------|------------------------|
| メトリクス | 「システム全体は健康か? 傾向は?」 | `orders_created_total`, `http.server.duration` |
| トレース | 「この1リクエストはどこで遅い/失敗した?」 | gateway→order→inventory のスパンツリー |
| ログ | 「その瞬間、コードは何と言っていた?」 | trace_id 付き構造化ログ |

重要なのは3本を**相関**させることです。
メトリクスの異常 (エラー率上昇) → 該当時間帯のトレース (どのサービスのどの呼び出しか)
→ そのトレースのログ (具体的なエラー内容) と掘り下げるのが実際の調査フローで、
そのために全サービスのログに `trace_id` を注入しています。

## 分散トレースの仕組み (このリポジトリで確認できること)

1. gateway が リクエストを受けると、FastAPI 計装がスパンを開始
2. gateway が order を httpx で呼ぶとき、計装が `traceparent: 00-<trace_id>-<span_id>-01`
   ヘッダーを**自動で**付与 (W3C Trace Context 標準)
3. order も同様に inventory へ伝播
4. Rust 側では `OtelAxumLayer` が traceparent を読み取り、同じ trace_id の子スパンを作る
5. 各サービスは自分のスパンだけを Collector に送り、バックエンド (Tempo 等) が
   trace_id で1本のツリーに組み立てる

**言語が違っても繋がる**のは、伝播がヘッダーという言語非依存の仕組みだからです。

## 計装コードの読みどころ

- `services/gateway/app/otel.py` — SDK の手動セットアップ。
  TracerProvider / MeterProvider / Exporter / Processor の関係が全部見える
- `services/order/app/main.py` — カスタムメトリクス (Counter, Histogram) と
  属性 (`result=success|out_of_stock`) の付け方
- `services/inventory/src/main.rs` — `#[instrument]` マクロによるスパン生成と、
  構造化フィールド (`info!(remaining = ...)`) の記録

Python は自動計装 CLI (`opentelemetry-instrument uvicorn ...`) を使えば
コード変更ゼロでも計装できますが、学習用にあえて手動にしています。

## Collector パイプラインの考え方

```
receivers (受口) → processors (加工) → exporters (送り先)
```

このリポジトリの設定 (`deploy/compose/otel-collector.yaml` 等) では:

- `otlp` receiver: アプリからの gRPC/HTTP を受ける
- `memory_limiter` / `batch` processor: 本番でもほぼ必須の2つ
- `k8sattributes` processor (EKS overlay): Pod/Deployment 名などを自動付与
- exporter を差し替えるだけで LGTM / Datadog / New Relic を切り替え

## Datadog に送る場合

1. Datadog アカウント作成 (14日トライアル)。日本なら site は `ap1.datadoghq.com`
2. API キーを取得し、Secret を作成:
   ```bash
   kubectl -n obs-lab create secret generic observability-keys \
     --from-literal=DD_API_KEY=<your-key>
   ```
3. `deploy/k8s/overlays/eks/otel-collector-config.yaml` の `datadog` exporter の
   コメントを外し、pipelines の exporters を `[datadog]` に変更して apply

補足: Datadog をフル活用する場合 (プロファイリング、セキュリティ機能等) は
公式の Datadog Agent (Helm/Operator) を DaemonSet で入れる方式が本流です。
OTel 経由は「ベンダー中立を保ちつつ Datadog の UI を使う」選択肢で、
APM・トレース・メトリクスの学習には十分です。両方式の違いを知ること自体に価値があります。

## New Relic に送る場合

New Relic は OTLP をネイティブに受けるため、専用 exporter すら不要です:

```yaml
exporters:
  otlphttp/newrelic:
    endpoint: https://otlp.nr-data.net
    headers:
      api-key: ${env:NEW_RELIC_LICENSE_KEY}
```

無料枠 (100GB/月, フルユーザー1名) が個人学習には十分寛大なので、
SaaS を1つだけ試すなら New Relic から始めるのがコスト的におすすめです。

## ここから深めるトピック

- **サンプリング**: 本番で全トレース保存は高コスト。head sampling
  (`traces_sampler`) と tail sampling (Collector の `tail_sampling` processor:
  「エラーと遅いものだけ全部残す」) の違いは実務で最重要級
- **SLO / エラーバジェット**: メトリクスから SLI を定義し、アラートを
  「症状ベース」(ユーザー影響) にする。Google SRE 本の中核概念
- **セマンティック規約**: `http.response.status_code` など属性名の標準。
  OTel の価値の半分はこの「共通語彙」にある
- **eBPF 自動計装**: 2026年のトレンド。コード変更なしでカーネルレベルから
  テレメトリを取る (Grafana Beyla, Datadog の eBPF ベース機能等)
