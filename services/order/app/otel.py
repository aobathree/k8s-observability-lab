"""OpenTelemetry 手動セットアップモジュール。

自動計装 (opentelemetry-instrument CLI) でも同じことができるが、
学習用に「何がどう設定されているか」を明示するため手動で構成している。

環境変数:
  OTEL_SERVICE_NAME            サービス名 (例: gateway)
  OTEL_EXPORTER_OTLP_ENDPOINT  OTLP gRPC エンドポイント (例: http://otel-collector:4317)
  OTEL_RESOURCE_ATTRIBUTES     追加のリソース属性 (例: deployment.environment=local)
"""

import logging

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_otel(app=None) -> None:
    """トレース・メトリクス・ログ相関の初期化。"""
    # Resource: サービス名などは OTEL_SERVICE_NAME / OTEL_RESOURCE_ATTRIBUTES
    # 環境変数から自動で読み込まれる
    resource = Resource.create()

    # --- Traces ---
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    # --- Metrics ---
    reader = PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=15_000)
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    # --- Logs: 標準ログに trace_id / span_id を注入 (ログとトレースの相関) ---
    LoggingInstrumentor().instrument(inject_trace_context=True)
    logging.basicConfig(
        level=logging.INFO,
        format=(
            '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s",'
            '"message":"%(message)s","trace_id":"%(otelTraceID)s","span_id":"%(otelSpanID)s"}'
        ),
    )

    # --- 自動計装: FastAPI (受信リクエスト) と httpx (送信リクエスト) ---
    if app is not None:
        FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
