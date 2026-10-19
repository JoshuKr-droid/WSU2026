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


# Applied Project Integration Test 2: a DynamoDB-managed target is checked and
# its website metrics are published to CloudWatch.
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

        assert target_url in webhealth.load_active_targets()
        monkeypatch.setattr(
            webhealth,
            "load_active_targets",
            lambda: [target_url],
        )

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
            Mock(side_effect=time.perf_counter),
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
        assert any(
            call.args[0] == target_url
            for call in urlopen.call_args_list
        )
        assert {
            "AVAILABILITY_METRIC",
            "LATENCY_METRIC",
            "HTTP_STATUS_CODE",
        }.issubset(metric_names)
    finally:
        table.delete_item(Key={"target_id": target_id})
        if created_local_table:
            aws_client("dynamodb").delete_table(TableName=table_name)


# Applied Project Integration Test 3: verifies the crawler reads active and
# paused targets from DynamoDB and only requests active websites.
def test_webhealth_crawls_only_active_dynamodb_targets(monkeypatch):
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

    active_id = unique_id("active-crawler-target")
    paused_id = unique_id("paused-crawler-target")
    active_url = f"https://{active_id}.example/"
    paused_url = f"https://{paused_id}.example/"
    table = aws_resource("dynamodb").Table(table_name)

    try:
        table.put_item(
            Item={
                "target_id": active_id,
                "url": active_url,
                "status": "active",
            }
        )
        table.put_item(
            Item={
                "target_id": paused_id,
                "url": paused_url,
                "status": "paused",
            }
        )

        importlib.invalidate_caches()
        webhealth = importlib.import_module("webhealth")
        webhealth = importlib.reload(webhealth)

        cloudwatch = Mock()
        operational_metrics = importlib.import_module("operational_metrics")
        monkeypatch.setattr(
            operational_metrics.boto3,
            "client",
            Mock(return_value=cloudwatch),
        )
        monkeypatch.setattr(webhealth.cw, "putDataFunc", Mock())

        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.getcode.return_value = 200
        urlopen = Mock(return_value=response)
        monkeypatch.setattr(webhealth.urllib.request, "urlopen", urlopen)

        result = webhealth.lambda_handler({}, None)
        requested_urls = [call.args[0] for call in urlopen.call_args_list]

        assert result["statusCode"] == 200
        assert active_url in requested_urls
        assert paused_url not in requested_urls
    finally:
        table.delete_item(Key={"target_id": active_id})
        table.delete_item(Key={"target_id": paused_id})
        if created_local_table:
            aws_client("dynamodb").delete_table(TableName=table_name)
