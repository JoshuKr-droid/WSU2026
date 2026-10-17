import importlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError


RESOURCE_DIR = Path(__file__).resolve().parents[2] / "joshua" / "resources"


@pytest.fixture
def rollback_handler(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-2")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("ROLLBACK_HISTORY_TABLE", "RollbackHistory")
    monkeypatch.setenv("FUNCTION_NAME", "web-health-test")
    monkeypatch.setenv("ALIAS_NAME", "Live")
    monkeypatch.syspath_prepend(str(RESOURCE_DIR))
    importlib.invalidate_caches()

    module = importlib.import_module("rollback_handler")
    module = importlib.reload(module)
    module.lambda_client = Mock()
    module.rollback_history = Mock()
    return module


def sns_event(
    alarm_name="CrawlerErrorAlarm",
    state="ALARM",
    description="Rollback trigger: crawler threw an error.",
):
    message = {
        "AlarmName": alarm_name,
        "NewStateValue": state,
        "StateChangeTime": "2026-10-17T00:00:00.000Z",
        "AlarmDescription": description,
    }
    return {
        "Records": [
            {"Sns": {"Message": json.dumps(message)}},
        ]
    }


def test_alarm_rolls_live_alias_back_to_previous_published_version(rollback_handler):
    rollback_handler.lambda_client.get_alias.return_value = {
        "FunctionVersion": "7",
        "RevisionId": "alias-revision",
    }
    rollback_handler.lambda_client.list_versions_by_function.side_effect = [
        {
            "Versions": [{"Version": "1"}, {"Version": "6"}],
            "NextMarker": "next-page",
        },
        {"Versions": [{"Version": "$LATEST"}, {"Version": "7"}]},
    ]

    result = rollback_handler.lambda_handler(sns_event(), None)

    rollback_handler.lambda_client.update_alias.assert_called_once_with(
        FunctionName="web-health-test",
        Name="Live",
        FunctionVersion="6",
        RevisionId="alias-revision",
    )
    rollback_handler.rollback_history.update_item.assert_called_once()
    assert result["results"][0]["to_version"] == "6"
    assert rollback_handler.rollback_history.put_item.call_count == 2


def test_non_operational_or_non_alarm_notifications_are_ignored(rollback_handler):
    result = rollback_handler.lambda_handler(
        sns_event(
            alarm_name="WebsiteAvailabilityAlarm0",
            description="Website is unavailable.",
        ),
        None,
    )
    assert result["results"][0]["status"] == "ignored"
    rollback_handler.lambda_client.get_alias.assert_not_called()

    result = rollback_handler.lambda_handler(sns_event(state="OK"), None)
    assert result["results"][0]["status"] == "ignored"
    rollback_handler.lambda_client.get_alias.assert_not_called()


def test_duplicate_alarm_state_change_does_not_roll_back_twice(rollback_handler):
    rollback_handler.lambda_client.get_alias.return_value = {
        "FunctionVersion": "7",
        "RevisionId": "alias-revision",
    }
    rollback_handler.rollback_history.put_item.side_effect = ClientError(
        {
            "Error": {
                "Code": "ConditionalCheckFailedException",
                "Message": "Already processed",
            }
        },
        "PutItem",
    )

    result = rollback_handler.lambda_handler(sns_event(), None)

    assert result["results"][0]["status"] == "already_processed_for_version"
    rollback_handler.lambda_client.get_alias.assert_called_once()


def test_rollback_fails_explicitly_when_no_previous_version_exists(rollback_handler):
    rollback_handler.lambda_client.get_alias.return_value = {
        "FunctionVersion": "1",
        "RevisionId": "alias-revision",
    }
    rollback_handler.lambda_client.list_versions_by_function.return_value = {
        "Versions": [{"Version": "$LATEST"}, {"Version": "1"}]
    }

    with pytest.raises(RuntimeError, match="No published Lambda version exists"):
        rollback_handler.lambda_handler(sns_event(), None)

    rollback_handler.lambda_client.update_alias.assert_not_called()
    rollback_handler.rollback_history.delete_item.assert_called_once_with(
        Key={"rollback_id": "ALIAS#web-health-test#Live"}
    )
