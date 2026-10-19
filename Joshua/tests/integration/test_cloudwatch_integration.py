import importlib
import os
import time
from pathlib import Path
from unittest.mock import Mock

from tests.integration.aws_test_support import (
    RUN_AWS_INTEGRATION_TESTS,
    aws_client,
    aws_resource,
    configure_boto3,
    create_targets_table,
    require_integration_environment,
    unique_id,
)


RESOURCE_DIR = Path(__file__).resolve().parents[2] / "joshua" / "resources"


def test_webhealth_publishes_metrics_to_cloudwatch(monkeypatch):
    # Gamma uses the deployed target table and CloudWatch; local runs can use LocalStack.
    if RUN_AWS_INTEGRATION_TESTS:
        require_integration_environment("CRAWLER_TARGETS_TABLE")
    else:
        require_integration_environment()

    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.syspath_prepend(str(RESOURCE_DIR))
    configure_boto3(monkeypatch)
    table_name = os.getenv("CRAWLER_TARGETS_TABLE")
    created_local_table = not table_name
    if created_local_table:
        table_name = unique_id("TestCrawlerTargets")
        create_targets_table(table_name)
        monkeypatch.setenv("CRAWLER_TARGETS_TABLE", table_name)

    target_id = unique_id("cloudwatch-target")
    target_url = f"https://{target_id}.example/"
    table = aws_resource("dynamodb").Table(table_name)
    table.put_item(
        Item={
            "target_id": target_id,
            "url": target_url,
            "status": "active",
        }
    )

    try:
        importlib.invalidate_caches()
        webhealth = importlib.import_module("webhealth")
        webhealth = importlib.reload(webhealth)

        published_metrics = []
        put_metric = webhealth.cw.putDataFunc

        def record_published_metric(namespace, name, url, value, unit):
            result = put_metric(namespace, name, url, value, unit)
            published_metrics.append((namespace, name, url, value, unit))
            return result

        monkeypatch.setattr(webhealth.cw, "putDataFunc", record_published_metric)
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.getcode.return_value = 200
        urlopen = Mock(return_value=response)
        monkeypatch.setattr(webhealth.urllib.request, "urlopen", urlopen)
        monkeypatch.setattr(
            webhealth.time,
            "monotonic",
            Mock(side_effect=[time.monotonic(), time.monotonic() + 0.5]),
        )

        result = webhealth.lambda_handler({}, None)

        metric_names = {
            name for namespace, name, url, _, _ in published_metrics
            if namespace == "WebHealth" and url == target_url
        }

        assert result == {
            "statusCode": 200,
            "body": "Metric publishing complete",
        }
        assert urlopen.call_args_list[0].args[0] == target_url
        assert {
            "AVAILABILITY_METRIC",
            "LATENCY_METRIC",
            "HTTP_STATUS_CODE",
        }.issubset(metric_names)
    finally:
        table.delete_item(Key={"target_id": target_id})
        if created_local_table:
            aws_client("dynamodb").delete_table(TableName=table_name)
