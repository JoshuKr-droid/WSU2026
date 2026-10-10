import importlib
import os
import urllib.request
from pathlib import Path
from unittest.mock import Mock

import boto3
import pytest


RESOURCE_DIR = Path(__file__).resolve().parents[2] / "joshua" / "resources"
LOCALSTACK_URL = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
AWS_REGION = "ap-southeast-2"
AWS_ACCESS_KEY_ID = "test"
AWS_SECRET_ACCESS_KEY = "test"

WEBSITE_URLS = [
    "https://www.westernsydney.edu.au/",
    "https://www.unsw.edu.au/",
    "https://www.sydney.edu.au/",
]


def _require_localstack():
    """Real AWS integration tests should only run when LocalStack is available."""
    try:
        with urllib.request.urlopen(f"{LOCALSTACK_URL}/_localstack/health", timeout=3) as response:
            if response.status != 200:
                raise RuntimeError(f"LocalStack health check returned {response.status}")
    except Exception as exc:  # pragma: no cover - only used in CI/local development
        pytest.skip(f"LocalStack is not running at {LOCALSTACK_URL}: {exc}")


def _aws_client(service_name):
    """Create a real boto3 client pointed at the LocalStack endpoint."""
    return boto3.client(
        service_name,
        region_name=AWS_REGION,
        endpoint_url=LOCALSTACK_URL,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def test_webhealth_publishes_metrics_to_cloudwatch(monkeypatch):
    # This is an integration test against the AWS API surface, not a mock of boto3.
    # LocalStack emulates AWS services locally so we can verify real writes to CloudWatch.
    _require_localstack()

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", AWS_ACCESS_KEY_ID)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", AWS_SECRET_ACCESS_KEY)
    monkeypatch.setenv("AWS_DEFAULT_REGION", AWS_REGION)

    monkeypatch.syspath_prepend(str(RESOURCE_DIR))
    importlib.invalidate_caches()

    webhealth = importlib.import_module("webhealth")
    webhealth = importlib.reload(webhealth)

    # Route the application code to LocalStack instead of the real AWS endpoint.
    monkeypatch.setattr(
        webhealth.boto3,
        "client",
        lambda service_name, **kwargs: _aws_client(service_name),
    )
    monkeypatch.setattr(
        webhealth.cw.boto3,
        "client",
        lambda service_name, **kwargs: _aws_client(service_name),
    )

    # Keep the dependency on external website availability isolated to the HTTP layer.
    responses = []
    for status_code in (200, 302, 503):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.getcode.return_value = status_code
        responses.append(response)

    monkeypatch.setattr(
        webhealth.urllib.request,
        "urlopen",
        Mock(side_effect=responses),
    )

    # Make latency deterministic so the service receives consistent metric values.
    monkeypatch.setattr(
        webhealth.time,
        "time",
        Mock(side_effect=[10.0, 10.5, 20.0, 21.0, 30.0, 32.0]),
    )

    result = webhealth.lambda_handler({}, None)

    cloudwatch = _aws_client("cloudwatch")
    metrics = cloudwatch.list_metrics(Namespace="WebHealth")
    metric_names = {metric["MetricName"] for metric in metrics["Metrics"]}

    assert result == {
        "statusCode": 200,
        "body": "Metric publishing complete",
    }
    assert {"AVAILABILITY_METRIC", "LATENCY_METRIC", "HTTP_STATUS_CODE"}.issubset(metric_names)
    assert any(
        dimension["Name"] == "URL" and dimension["Value"] == WEBSITE_URLS[0]
        for metric in metrics["Metrics"]
        for dimension in metric.get("Dimensions", [])
    )