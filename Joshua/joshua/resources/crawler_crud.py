import json
import logging
import os
from urllib.parse import urlsplit

import boto3
from botocore.exceptions import ClientError
from operational_metrics import measure_dynamodb_operation


logger = logging.getLogger(__name__)
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["CRAWLER_TARGETS_TABLE"])
VALID_STATUSES = {"active", "paused"}
MAX_TARGET_ID_LENGTH = 256


def _response(status_code, payload):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(payload),
    }


def _parse_body(event):
    body = event.get("body")
    if not body:
        return {}
    if not isinstance(body, str):
        raise ValueError("Request body must be a JSON object.")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise ValueError("Request body must contain valid JSON.") from error

    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    return payload


def _validate_target_id(target_id):
    if not isinstance(target_id, str) or not target_id.strip():
        raise ValueError("target_id must be a non-empty string.")
    target_id = target_id.strip()
    if len(target_id) > MAX_TARGET_ID_LENGTH:
        raise ValueError(
            f"target_id must be no longer than {MAX_TARGET_ID_LENGTH} characters."
        )
    return target_id


def _validate_url(url):
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url must be a non-empty HTTP or HTTPS URL.")
    url = url.strip()
    try:
        parsed_url = urlsplit(url)
        hostname = parsed_url.hostname
        _ = parsed_url.port
    except ValueError as error:
        raise ValueError("url must be a valid HTTP or HTTPS URL.") from error
    if (
        any(character.isspace() for character in url)
        or parsed_url.scheme.lower() not in {"http", "https"}
        or not parsed_url.netloc
        or not hostname
        or parsed_url.username
        or parsed_url.password
    ):
        raise ValueError("url must be a valid HTTP or HTTPS URL without credentials.")
    return url


def _scan_all_targets():
    items = []
    scan_kwargs = {}
    while True:
        response = measure_dynamodb_operation(
            "list_targets",
            "Read",
            lambda: table.scan(**scan_kwargs),
        )
        items.extend(response.get("Items", []))
        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            return items
        # DynamoDB Scan is paginated; retain the cursor to return every target.
        scan_kwargs["ExclusiveStartKey"] = last_evaluated_key


def lambda_handler(event, context):
    http_method = event.get("httpMethod")
    if isinstance(http_method, str):
        http_method = http_method.upper()
    path_parameters = event.get("pathParameters") or {}

    try:
        if http_method == "GET":
            target_id = path_parameters.get("target_id")
            if target_id is not None:
                target_id = _validate_target_id(target_id)
                response = measure_dynamodb_operation(
                    "get_target",
                    "Read",
                    lambda: table.get_item(Key={"target_id": target_id}),
                )
                item = response.get("Item")
                if not item:
                    return _response(404, {"error": "Target not found."})
                return _response(200, item)
            return _response(200, _scan_all_targets())

        if http_method == "POST":
            body = _parse_body(event)
            unexpected_fields = set(body) - {"target_id", "url"}
            if unexpected_fields:
                return _response(
                    400,
                    {"error": "Only target_id and url are allowed when creating a target."},
                )
            target_id = _validate_target_id(body.get("target_id"))
            url = _validate_url(body.get("url"))
            measure_dynamodb_operation(
                "create_target",
                "Write",
                lambda: table.put_item(
                    Item={"target_id": target_id, "url": url, "status": "active"},
                    # Prevent a repeated ID from silently replacing an existing target.
                    ConditionExpression="attribute_not_exists(target_id)",
                ),
            )
            return _response(
                201,
                {
                    "target_id": target_id,
                    "url": url,
                    "status": "active",
                },
            )

        if http_method == "PUT":
            target_id = path_parameters.get("target_id")
            if target_id is None:
                return _response(400, {"error": "target_id is required in the path."})
            target_id = _validate_target_id(target_id)

            body = _parse_body(event)
            unexpected_fields = set(body) - {"url", "status"}
            if unexpected_fields:
                return _response(
                    400,
                    {"error": "Only url and status can be updated."},
                )
            if not body:
                return _response(
                    400,
                    {"error": "Provide at least one field to update: url or status."},
                )

            updates = {}
            if "url" in body:
                updates["url"] = _validate_url(body["url"])
            if "status" in body:
                status = body["status"]
                if not isinstance(status, str) or status not in VALID_STATUSES:
                    return _response(
                        400,
                        {"error": "status must be either 'active' or 'paused'."},
                    )
                updates["status"] = status

            expression_names = {f"#{field}": field for field in updates}
            expression_values = {f":{field}": value for field, value in updates.items()}
            update_expression = "SET " + ", ".join(
                f"#{field} = :{field}" for field in updates
            )
            response = measure_dynamodb_operation(
                "update_target",
                "Write",
                lambda: table.update_item(
                    Key={"target_id": target_id},
                    UpdateExpression=update_expression,
                    # Avoid DynamoDB creating a partial item for an unknown ID.
                    ConditionExpression="attribute_exists(target_id)",
                    ExpressionAttributeNames=expression_names,
                    ExpressionAttributeValues=expression_values,
                    ReturnValues="ALL_NEW",
                ),
            )
            return _response(200, response["Attributes"])

        if http_method == "DELETE":
            target_id = path_parameters.get("target_id")
            if target_id is None:
                return _response(400, {"error": "target_id is required in the path."})
            target_id = _validate_target_id(target_id)
            response = measure_dynamodb_operation(
                "delete_target",
                "Write",
                lambda: table.delete_item(
                    Key={"target_id": target_id},
                    # Return 404 rather than treating a missing target as deleted.
                    ConditionExpression="attribute_exists(target_id)",
                    ReturnValues="ALL_OLD",
                ),
            )
            return _response(200, response["Attributes"])

        return _response(405, {"error": "Method not allowed."})

    except ValueError as error:
        return _response(400, {"error": str(error)})
    except ClientError as error:
        error_code = error.response.get("Error", {}).get("Code")
        if error_code == "ConditionalCheckFailedException":
            if http_method == "POST":
                return _response(409, {"error": "A target with this target_id already exists."})
            if http_method in {"PUT", "DELETE"}:
                return _response(404, {"error": "Target not found."})
        logger.exception("DynamoDB request failed while handling %s.", http_method)
        return _response(500, {"error": "The target operation could not be completed."})
