import importlib
import json
import os
import urllib.request
from pathlib import Path

import boto3
import pytest


RESOURCE_DIR = Path(__file__).resolve().parents[2] / "joshua" / "resources"
LOCALSTACK_URL = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
AWS_REGION = "ap-southeast-2"
AWS_ACCESS_KEY_ID = "test"
AWS_SECRET_ACCESS_KEY = "test"
TABLE_NAME = "TestAlarmLogTable"


def _require_localstack():
    """These tests must hit a real AWS-compatible service endpoint, not a stubbed SDK client."""
    try:
        with urllib.request.urlopen(f"{LOCALSTACK_URL}/_localstack/health", timeout=3) as response:
            if response.status != 200:
                raise RuntimeError(f"LocalStack health check returned {response.status}")
    except Exception as exc:  # pragma: no cover - the suite should skip when LocalStack is not running
        pytest.skip(f"LocalStack is not running at {LOCALSTACK_URL}: {exc}")


def _aws_client(service_name):
    """Create a boto3 client pointed at LocalStack to preserve real service integration."""
    return boto3.client(
        service_name,
        region_name=AWS_REGION,
        endpoint_url=LOCALSTACK_URL,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def _aws_resource(service_name):
    """Create a boto3 resource pointed at LocalStack for a real DynamoDB table write/read cycle."""
    return boto3.resource(
        service_name,
        region_name=AWS_REGION,
        endpoint_url=LOCALSTACK_URL,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def test_alarm_notification_is_written_to_dynamodb(monkeypatch):
    # This is a true service-level integration test: the Lambda writes to a real DynamoDB table.
    # We intentionally skip it when LocalStack is not available so the suite stays reliable in CI.
    _require_localstack()

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", AWS_ACCESS_KEY_ID)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", AWS_SECRET_ACCESS_KEY)
    monkeypatch.setenv("AWS_DEFAULT_REGION", AWS_REGION)
    monkeypatch.setenv("ALARM_LOG_TABLE", TABLE_NAME)

    monkeypatch.syspath_prepend(str(RESOURCE_DIR))
    importlib.invalidate_caches()

    # Create the real DynamoDB table before the Lambda executes.
    client = _aws_client("dynamodb")
    client.create_table(
        TableName=TABLE_NAME,
        KeySchema=[{"AttributeName": "alarm_name", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "alarm_name", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    client.get_waiter("table_exists").wait(TableName=TABLE_NAME)

    # Point the application to LocalStack instead of the live AWS endpoint.
    monkeypatch.setattr(
        boto3,
        "resource",
        lambda service_name, **kwargs: _aws_resource(service_name),
    )

    # Import the Lambda after setting the environment so the module-level table binding is created
    # against the correct LocalStack-backed DynamoDB resource.
    alarmlogger = importlib.import_module("alarm_logger")
    alarmlogger = importlib.reload(alarmlogger)

    message = {
        "AlarmName": "WebsiteAvailabilityAlarm0",
        "StateChangeTime": "2026-10-10T00:00:00.000Z",
        "NewStateValue": "ALARM",
        "NewStateReason": "Website availability dropped below threshold",
        "Region": "ap-southeast-2",
        "AWSAccountId": "123456789012",
    }
    raw_message = json.dumps(message)

    event = {
        "Records": [
            {"Sns": {"Message": raw_message}}
        ]
    }

    result = alarmlogger.lambda_handler(event, None)

    # Read the persisted item back from the real DynamoDB table to confirm the write really happened.
    table = _aws_resource("dynamodb").Table(TABLE_NAME)
    stored = table.get_item(Key={"alarm_name": message["AlarmName"]})

    assert result == {"body": "Alarm notification logged"}
    assert stored["Item"]["alarm_name"] == "WebsiteAvailabilityAlarm0"
    assert stored["Item"]["new_state"] == "ALARM"
    assert stored["Item"]["reason"] == "Website availability dropped below threshold"
    assert stored["Item"]["raw_message"] == raw_message