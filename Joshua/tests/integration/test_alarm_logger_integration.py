import importlib
import json
import os
from pathlib import Path

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


def test_alarm_notification_is_written_to_dynamodb(monkeypatch):
    # Gamma uses the deployed alarm table. Local runs can use a temporary LocalStack table.
    if RUN_AWS_INTEGRATION_TESTS:
        require_integration_environment("ALARM_LOG_TABLE")
    else:
        require_integration_environment()

    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.syspath_prepend(str(RESOURCE_DIR))
    configure_boto3(monkeypatch)

    table_name = os.getenv("ALARM_LOG_TABLE")
    created_local_table = not table_name
    if created_local_table:
        table_name = unique_id("TestAlarmLog")
        create_test_table(table_name, "alarm_name", "state_change_time")
        monkeypatch.setenv("ALARM_LOG_TABLE", table_name)

    alarm_name = unique_id("IntegrationAlarm")
    state_change_time = "2026-10-19T08:00:00.000Z"
    message = {
        "AlarmName": alarm_name,
        "StateChangeTime": state_change_time,
        "NewStateValue": "ALARM",
        "NewStateReason": "Integration test alarm",
        "Region": "ap-southeast-2",
        "AWSAccountId": "123456789012",
    }
    raw_message = json.dumps(message)
    event = {"Records": [{"Sns": {"Message": raw_message}}]}

    try:
        alarmlogger = importlib.import_module("alarm_logger")
        alarmlogger = importlib.reload(alarmlogger)
        result = alarmlogger.lambda_handler(event, None)

        table = aws_resource("dynamodb").Table(table_name)
        stored = table.get_item(
            Key={
                "alarm_name": alarm_name,
                "state_change_time": state_change_time,
            }
        )

        assert result == {"body": "Alarm notification logged"}
        assert stored["Item"]["alarm_name"] == alarm_name
        assert stored["Item"]["new_state"] == "ALARM"
        assert stored["Item"]["reason"] == "Integration test alarm"
        assert stored["Item"]["raw_message"] == raw_message
    finally:
        table = aws_resource("dynamodb").Table(table_name)
        table.delete_item(
            Key={
                "alarm_name": alarm_name,
                "state_change_time": state_change_time,
            }
        )
        if created_local_table:
            aws_client("dynamodb").delete_table(TableName=table_name)
