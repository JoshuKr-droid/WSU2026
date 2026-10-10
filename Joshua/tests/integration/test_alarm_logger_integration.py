import importlib
import json
import sys
from pathlib import Path

import boto3
from botocore.stub import Stubber


RESOURCE_DIR = Path(__file__).resolve().parents[2] / "joshua" / "resources"


def test_alarm_notification_is_written_to_dynamodb(monkeypatch):
    # Provide dummy credentials and a region for local testing.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-2")
    monkeypatch.setenv("ALARM_LOG_TABLE", "TestAlarmLogTable")

    monkeypatch.syspath_prepend(str(RESOURCE_DIR))
    importlib.invalidate_caches()

    # Create a real DynamoDB resource with a stubbed API client.
    dynamodb = boto3.resource("dynamodb", region_name="ap-southeast-2")
    stubber = Stubber(dynamodb.meta.client)

    # Ensure the Lambda module uses our resource.
    monkeypatch.setattr(
        boto3,
        "resource",
        lambda service_name, **kwargs: dynamodb,
    )

    # Import after setting the environment variable because the table
    # is created when alarmlogger.py is imported.
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
            {
                "Sns": {
                    "Message": raw_message,
                }
            }
        ]
    }

    # DynamoDB's low-level API expects AttributeValue structures.
    expected_item = {
        "alarm_name": message["AlarmName"],
        "state_change_time": message["StateChangeTime"],
        "new_state": message["NewStateValue"],
        "reason": message["NewStateReason"],
        "region": message["Region"],
        "account_id": message["AWSAccountId"],
        "raw_message": raw_message,
    }

    stubber.add_response(
        "put_item",
        {},
        {
            "TableName": "TestAlarmLogTable",
            "Item": expected_item,
        },
    )

    with stubber:
        result = alarmlogger.lambda_handler(event, None)
        stubber.assert_no_pending_responses()

    assert result == {"body": "Alarm notification logged"}