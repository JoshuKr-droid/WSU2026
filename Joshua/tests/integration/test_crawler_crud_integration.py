import importlib
import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from tests.integration.aws_test_support import (
    RUN_AWS_INTEGRATION_TESTS,
    aws_client,
    aws_resource,
    configure_boto3,
    create_test_table,
    require_integration_environment,
    unique_id,
)


RESOURCE_DIR = Path(__file__).resolve().parents[2] / "joshua" / "resources"


def _event(method, body=None, target_id=None):
    return {
        "httpMethod": method,
        "pathParameters": {"target_id": target_id} if target_id else None,
        "body": json.dumps(body) if body is not None else None,
    }


def _body(response):
    return json.loads(response["body"])


# Applied Project Integration Test 1: exercises create, list, fetch, update,
# and delete through the CRUD Lambda against a real DynamoDB table. It verifies
# read/write latency metric emission, and removes its test item afterward.
def test_target_crud_lifecycle_against_dynamodb_and_latency_metrics(monkeypatch):
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
        monkeypatch.setenv("CRAWLER_TARGETS_TABLE", table_name)
        client = aws_client("dynamodb")
        client.create_table(
            TableName=table_name,
            KeySchema=[{"AttributeName": "target_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "target_id", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        client.get_waiter("table_exists").wait(TableName=table_name)

    target_id = unique_id("site")
    table = aws_resource("dynamodb").Table(table_name)
    cloudwatch = Mock()
    try:
        crud = importlib.import_module("crawler_crud")
        crud = importlib.reload(crud)
        crud.table = table
        operational_metrics = importlib.import_module("operational_metrics")
        monkeypatch.setattr(
            operational_metrics.boto3,
            "client",
            Mock(return_value=cloudwatch),
        )

        created = crud.lambda_handler(
            _event(
                "POST",
                {"target_id": target_id, "url": "https://example.com"},
            ),
            None,
        )
        fetched = crud.lambda_handler(_event("GET", target_id=target_id), None)
        listed = crud.lambda_handler(_event("GET"), None)
        updated = crud.lambda_handler(
            _event(
                "PUT",
                {"url": "https://updated.example/path", "status": "paused"},
                target_id,
            ),
            None,
        )
        deleted = crud.lambda_handler(
            _event("DELETE", target_id=target_id),
            None,
        )
        missing = crud.lambda_handler(_event("GET", target_id=target_id), None)

        assert created["statusCode"] == 201
        assert fetched["statusCode"] == 200
        assert _body(fetched)["url"] == "https://example.com"
        assert listed["statusCode"] == 200
        assert any(item["target_id"] == target_id for item in _body(listed))
        assert updated["statusCode"] == 200
        assert _body(updated)["status"] == "paused"
        assert _body(updated)["url"] == "https://updated.example/path"
        assert deleted["statusCode"] == 200
        assert _body(deleted)["target_id"] == target_id
        assert missing["statusCode"] == 404

        metric_names = [
            call.kwargs["MetricData"][0]["MetricName"]
            for call in cloudwatch.put_metric_data.call_args_list
        ]
        assert "DynamoDBReadLatency" in metric_names
        assert "DynamoDBWriteLatency" in metric_names
        assert metric_names.count("DynamoDBWriteLatency") == 3
    finally:
        table.delete_item(Key={"target_id": target_id})
        if created_local_table:
            aws_client("dynamodb").delete_table(TableName=table_name)
