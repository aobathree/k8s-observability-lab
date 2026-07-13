# EKS 移行手順

kind で動かしたものと**同じ base マニフェスト**を EKS に載せます。
差分は overlays/eks (ECR イメージ / SaaS exporter / RBAC) だけです。

## 前提ツール

```bash
# aws cli v2, eksctl, kubectl, docker が必要
aws --version && eksctl version && kubectl version --client
aws sts get-caller-identity   # 認証確認
```

## 1. クラスタ作成 (約20分)

```bash
eksctl create cluster \
  --name obs-lab \
  --region ap-northeast-1 \
  --nodegroup-name workers \
  --node-type t3.medium \
  --nodes 2
```

eksctl が VPC・サブネット・IAM ロール・Managed Node Group まで一式作り、
kubeconfig も設定してくれます。

> **コスト**: EKS コントロールプレーン ~$0.10/時 + t3.medium×2 ~$0.11/時。
> 1日つけっぱなしで約 $5。**学習後は必ず削除**:
> `eksctl delete cluster --name obs-lab --region ap-northeast-1`

## 2. ECR へイメージを push

```bash
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export REGION=ap-northeast-1
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

for svc in gateway order inventory; do
  aws ecr create-repository --repository-name obs-lab/$svc --region $REGION || true
  docker build -t $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/obs-lab/$svc:v0.1.0 services/$svc
  docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/obs-lab/$svc:v0.1.0
done
```

> Apple Silicon 等 ARM マシンでビルドする場合は
> `docker build --platform linux/amd64` を付けること (ノードは x86_64)。

## 3. overlay の書き換えとデプロイ

`deploy/k8s/overlays/eks/kustomization.yaml` の `<ACCOUNT_ID>` を自分の
アカウント ID に置換してから:

```bash
# SaaS のキーを Secret に (Datadog / New Relic を使う場合)
kubectl create namespace obs-lab
kubectl -n obs-lab create secret generic observability-keys \
  --from-literal=DD_API_KEY=xxxx \
  --from-literal=NEW_RELIC_LICENSE_KEY=xxxx

kubectl apply -k deploy/k8s/overlays/eks
kubectl -n obs-lab get pods -w
```

## 4. 動作確認と観察

```bash
kubectl -n obs-lab port-forward svc/gateway 8080:8000 &
python scripts/loadgen.py

# Collector が受信しているかログで確認
kubectl -n obs-lab logs deploy/otel-collector --tail=20
```

exporter を Datadog / New Relic に切り替えていれば (otel-collector-config.yaml)、
数分以内に SaaS 側の APM / Distributed Tracing 画面にサービスマップが現れます。

## 5. EKS ならではの発展課題

1. **kubectl drain でノードを1台落とす** → Pod が再スケジュールされる様子と、
   その間のエラー率をダッシュボードで観察 (これぞ Observability の使いどころ)
2. **HPA**: `kubectl autoscale deployment gateway --min 2 --max 5 --cpu-percent=50`
   → loadgen の rps を上げてスケールアウトを観察
3. **AWS Load Balancer Controller** を入れて Ingress で公開
4. **IAM Roles for Service Accounts (IRSA) / Pod Identity**: Pod に AWS 権限を
   与える EKS 固有の重要概念。S3 読み書きするサービスを足すと学べる
5. **Karpenter**: 2026年時点のノードオートスケーラー本命。Cluster Autoscaler との違いを調べる
6. **CloudWatch Container Insights** を有効化し、SaaS との情報量・体験差を比較

## 片付け

```bash
eksctl delete cluster --name obs-lab --region ap-northeast-1
# ECR リポジトリも消す場合
for svc in gateway order inventory; do
  aws ecr delete-repository --repository-name obs-lab/$svc --region ap-northeast-1 --force
done
```
