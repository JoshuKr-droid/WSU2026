import json
import os

import boto3


table = boto3.resource("dynamodb").Table(os.environ["ALARM_LOG_TABLE"])


def lambda_handler(event, context):
	for record in event.get("Records", []):
		message = json.loads(record["Sns"]["Message"])

		table.put_item(
			Item={
				"alarm_name": message["AlarmName"],
				"state_change_time": message["StateChangeTime"],
				"new_state": message["NewStateValue"],
				"reason": message["NewStateReason"],
				"region": message.get("Region"),
				"account_id": message.get("AWSAccountId"),
				"raw_message": record["Sns"]["Message"],
			}
		)

	return {"body": "Alarm notification logged"}
