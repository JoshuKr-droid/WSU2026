import importlib
import json
import os
import urllib.request
import uuid
from pathlib import Path
from unittest.mock import Mock

import boto3
import pytest


RESOURCE_DIR = Path(__file__).resolve().parents[2] / "joshua" / "resources"
LOCALSTACK_URL = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
AWS_REGION = "ap-southeast-2"
AWS_ACCESS_KEY_ID = "test"
AWS_SECRET_ACCESS_KEY = "test"


def _require_localstack():
    try:
        with urllib.request.urlopen(
            f"{LOCALSTACK_URL}/_localstack/health",
            timeout=3,
        ) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"LocalStack health check returned {response.status}"
                )
    except Exception as error:  # pragma: no cover - depends on local test service
        pytest.skip(f"LocalStack is not running at {LOCALSTACK_URL}: {error}")


def _aws_client(service_name):
    return boto3.client(
        service_name,
        region_name=AWS_REGION,
        endpoint_url=LOCALSTACK_URL,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def _aws_resource(service_name):
    return boto3.resource(
        service_name,
        region_name=AWS_REGION,
        endpoint_url=LOCALSTACK_URL,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def _event(method, body=None, target_id=None):
    return {
        "httpMethod": method,
        "pathParameters": {"target_id": target_id} if target_id else None,
        "body": json.dumps(body) if body is not None else None,
    }


def _body(response):
    return json.loads(response["body"])


# Applied Project Integration Test 1: exercises create, list, fetch, update,
# and delete through the CRUD Lambda against a real LocalStack DynamoDB table.
# It also checks that the CRUD reads and writes emit latency metrics.
def test_target_crud_lifecycle_against_dynamodb_and_latency_metrics(monkeypatch):
    _require_localstack()

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", AWS_ACCESS_KEY_ID)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", AWS_SECRET_ACCESS_KEY)
    monkeypatch.setenv("AWS_DEFAULT_REGION", AWS_REGION)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    table_name = f"TestCrawlerTargets{uuid.uuid4().hex[:12]}"
    monkeypatch.setenv("CRAWLER_TARGETS_TABLE", table_name)
    monkeypatch.syspath_prepend(str(RESOURCE_DIR))
    importlib.invalidate_caches()

    client = _aws_client("dynamodb")
    client.create_table(
        TableName=table_name,
        KeySchema=[{"AttributeName": "target_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "target_id", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    client.get_waiter("table_exists").wait(TableName=table_name)

    cloudwatch = Mock()
    try:
        crud = importlib.import_module("crawler_crud")
        crud = importlib.reload(crud)
        crud.table = _aws_resource("dynamodb").Table(table_name)
        operational_metrics = importlib.import_module("operational_metrics")
        monkeypatch.setattr(
            operational_metrics.boto3,
            "client",
            Mock(return_value=cloudwatch),
        )

        created = crud.lambda_handler(
            _event(
                "POST",
                {"target_id": "site-1", "url": "https://example.com"},
            ),
            None,
        )
        fetched = crud.lambda_handler(_event("GET", target_id="site-1"), None)
        listed = crud.lambda_handler(_event("GET"), None)
        updated = crud.lambda_handler(
            _event(
                "PUT",
                {"url": "https://updated.example/path", "status": "paused"},
                "site-1",
            ),
            None,
        )
        deleted = crud.lambda_handler(
            _event("DELETE", target_id="site-1"),
            None,
        )
        missing = crud.lambda_handler(_event("GET", target_id="site-1"), None)

        assert created["statusCode"] == 201
        assert fetched["statusCode"] == 200
        assert _body(fetched)["url"] == "https://example.com"
        assert listed["statusCode"] == 200
        assert _body(listed)[0]["target_id"] == "site-1"
        assert updated["statusCode"] == 200
        assert _body(updated)["status"] == "paused"
        assert _body(updated)["url"] == "https://updated.example/path"
        assert deleted["statusCode"] == 200
        assert _body(deleted)["target_id"] == "site-1"
        assert missing["statusCode"] == 404

        metric_names = [
            call.kwargs["MetricData"][0]["MetricName"]
            for call in cloudwatch.put_metric_data.call_args_list
        ]
        assert "DynamoDBReadLatency" in metric_names
        assert "DynamoDBWriteLatency" in metric_names
        assert metric_names.count("DynamoDBWriteLatency") == 3
    finally:
        client.delete_table(TableName=table_name)
