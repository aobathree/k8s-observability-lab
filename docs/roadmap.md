# 学習ロードマップ

対象: 2019〜2020年に Kubernetes / マイクロサービスの座学経験があり、
実地経験がない方。2026年の現在地までのアップデートを含みます。

## まず: 2019年の知識からの主な変化

当時の書籍・研修の知識は土台としてそのまま有効です。概念 (Pod, Service,
Deployment, 宣言的管理) は変わっていません。変わった点を押さえれば追いつけます。

| 2019年ごろの常識 | 2026年の現在 |
|---|---|
| ランタイムは Docker | Dockershim 廃止 (k8s 1.24)。ランタイムは containerd。ただし開発時のイメージビルドに docker を使うのは変わらず |
| PodSecurityPolicy | 廃止 → Pod Security Admission (PSA) に置き換え |
| Ingress が公開の基本 | Ingress は現役だが、後継の **Gateway API** が GA になり移行が進む |
| 監視は Prometheus + Jaeger/Zipkin 等バラバラ | **OpenTelemetry がテレメトリ標準として確立**。トレース/メトリクス/ログを単一 SDK・単一プロトコル (OTLP) で扱う |
| デプロイは kubectl/Helm 手動 | **GitOps (ArgoCD / Flux) が本番の標準形**。Git が唯一の真実源 |
| サービスメッシュ = Istio (サイドカー) | サイドカーレス化が進む (Istio ambient, Cilium/eBPF)。「本当にメッシュが必要か」を問うのが主流に |
| ノードスケール = Cluster Autoscaler | AWS では **Karpenter** が本命に |
| 観測 = 「監視 (Monitoring)」 | 「Observability」へ。既知の障害を監視するのでなく、未知の問題を調査可能にする、という考え方の転換 |

## フェーズ 1: コンテナと計装の基礎固め (半日〜1日)

- [ ] このリポジトリを docker compose で起動し、README の手順で3本柱を観察する
- [ ] `services/gateway/app/otel.py` を読み、TracerProvider → Processor → Exporter の流れを説明できるようにする
- [ ] product_id 99 / 999 の異常をトレースで特定する練習
- [ ] Collector の設定を1箇所変えてみる (例: debug exporter の verbosity を detailed に)

**ゴール**: 「トレースとは何か」を画面を見ながら人に説明できる。

## フェーズ 2: ローカル Kubernetes (1週間)

- [ ] kind でクラスタを作り、overlays/local-kind をデプロイ
- [ ] `kubectl describe pod` / `logs` / `port-forward` / `exec` を手癖にする
- [ ] kustomize の base/overlay 差分を説明できるようにする
- [ ] Pod を `kubectl delete pod` で殺し、Deployment が復旧する様子とその間のテレメトリを観察
- [ ] inventory を replicas: 2 にして「何が壊れるか」を確認 (在庫の分裂)
- [ ] readiness/liveness probe を一時的に壊して挙動を観察

**ゴール**: マニフェストを恐れず読める・書ける。障害時にまず何を打つか体が覚えている。

## フェーズ 3: EKS 実地 (1〜2週間, 数十ドル)

- [ ] docs/eks-migration.md の手順で EKS デプロイ
- [ ] New Relic (無料枠) か Datadog (トライアル) に接続し、サービスマップを見る
- [ ] ノード drain / HPA / IRSA の発展課題 (eks-migration.md §5)
- [ ] 毎回クラスタを消す運用を徹底 → 自然と「再現可能なインフラ」の感覚が身につく

**ゴール**: 「AWS 上に k8s でマイクロサービスを立てて SaaS で観測した」と言える。

## フェーズ 4: 深化 (1〜3ヶ月, 興味に応じて)

**Observability を深める**:
- [ ] tail sampling (エラーと遅いトレースだけ残す) を Collector に設定
- [ ] SLO を定義しアラートを作る (例: 「注文成功率 99% / 30日」)
- [ ] Rust サービスにカスタムメトリクスを追加 (opentelemetry meter API)

**マイクロサービスを深める**:
- [ ] order → 通知サービスを SQS 経由の非同期にし、トレースがどう分断されるか・
      span link でどう繋ぐかを学ぶ
- [ ] 障害注入: inventory への呼び出しにタイムアウト+リトライ+サーキットブレーカーを実装

**Kubernetes を深める**:
- [ ] GitOps: ArgoCD を入れて「git push でデプロイ」にする
- [ ] Gateway API で公開してみる
- [ ] Helm チャート化してみる (kustomize との使い分けを体感)

**Rust を深める**:
- [ ] inventory に SQLite/Postgres (sqlx) を足して永続化
- [ ] gateway を axum で書き直し、FastAPI 版とレイテンシ・メモリ使用量を
      ダッシュボードで比較する (これ自体が最高の Observability 演習)

## 参考リソース

- OpenTelemetry 公式ドキュメント (https://opentelemetry.io/docs/) — まずここ
- 『オブザーバビリティ・エンジニアリング』(O'Reilly) — 考え方の背骨
- Google SRE Book (https://sre.google/books/) — SLO/エラーバジェット
- EKS Best Practices Guide (https://docs.aws.amazon.com/eks/latest/best-practices/)
- kustomize / kind / eksctl の各公式ドキュメント
