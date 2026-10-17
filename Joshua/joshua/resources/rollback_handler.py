import json
import os

import boto3
from botocore.exceptions import ClientError


lambda_client = boto3.client("lambda")
rollback_history = boto3.resource("dynamodb").Table(
    os.environ["ROLLBACK_HISTORY_TABLE"]
)
function_name = os.environ["FUNCTION_NAME"]
alias_name = os.environ["ALIAS_NAME"]


def _previous_version(current_version):
    current = int(current_version)
    versions = []
    marker = None

    while True:
        request = {"FunctionName": function_name}
        if marker:
            request["Marker"] = marker
        response = lambda_client.list_versions_by_function(**request)
        versions.extend(
            int(version["Version"])
            for version in response["Versions"]
            if version["Version"].isdigit()
            and int(version["Version"]) < current
        )
        marker = response.get("NextMarker")
        if not marker:
            break

    if not versions:
        raise RuntimeError(
            f"No published Lambda version exists before version {current}."
        )
    return str(max(versions))


def _rollback_alarm(message):
    alarm_name = message.get("AlarmName")
    alarm_description = message.get("AlarmDescription", "")
    if (
        message.get("NewStateValue") != "ALARM"
        or not alarm_description.startswith("Rollback trigger:")
    ):
        return {"status": "ignored", "alarm": alarm_name}

    state_change_time = message.get("StateChangeTime")
    if not alarm_name or not state_change_time:
        raise ValueError("Alarm notification is missing its name or state-change time.")

    alias_lock_id = f"ALIAS#{function_name}#{alias_name}"
    alias = lambda_client.get_alias(
        FunctionName=function_name,
        Name=alias_name,
    )
    current_version = alias["FunctionVersion"]
    try:
        rollback_history.put_item(
            Item={
                "rollback_id": alias_lock_id,
                "current_version": current_version,
                "rolled_back_to": current_version,
                "alarm_name": alarm_name,
                "state_change_time": state_change_time,
                "status": "IN_PROGRESS",
            },
            ConditionExpression=(
                "attribute_not_exists(rollback_id) OR rolled_back_to <> :current"
            ),
            ExpressionAttributeValues={":current": current_version},
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return {"status": "already_processed_for_version", "alarm": alarm_name}
        raise

    alias_updated = False
    try:
        previous_version = _previous_version(current_version)
        lambda_client.update_alias(
            FunctionName=function_name,
            Name=alias_name,
            FunctionVersion=previous_version,
            RevisionId=alias["RevisionId"],
        )
        alias_updated = True
        rollback_history.update_item(
            Key={"rollback_id": alias_lock_id},
            UpdateExpression="SET #status = :status, rolled_back_to = :previous",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": "ROLLED_BACK",
                ":previous": previous_version,
            },
        )
        rollback_history.put_item(
            Item={
                "rollback_id": f"EVENT#{state_change_time}#{alarm_name}",
                "alarm_name": alarm_name,
                "state_change_time": state_change_time,
                "from_version": current_version,
                "to_version": previous_version,
                "status": "ROLLED_BACK",
            }
        )
    except Exception:
        if not alias_updated:
            rollback_history.delete_item(Key={"rollback_id": alias_lock_id})
        raise

    print(
        f"Rolled alias {alias_name} back from version {current_version} "
        f"to version {previous_version} after {alarm_name}."
    )
    return {
        "status": "rolled_back",
        "alarm": alarm_name,
        "from_version": current_version,
        "to_version": previous_version,
    }


def lambda_handler(event, context):
    results = []
    for record in event.get("Records", []):
        sns_record = record.get("Sns")
        if not sns_record or "Message" not in sns_record:
            raise ValueError("Event record is missing an SNS message.")
        message = json.loads(sns_record["Message"])
        results.append(_rollback_alarm(message))
    return {"results": results}
