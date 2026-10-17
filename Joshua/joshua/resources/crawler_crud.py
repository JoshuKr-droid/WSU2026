import json
import os
import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
table_name = os.environ.get("CRAWLER_TARGETS_TABLE")
table = dynamodb.Table(table_name)

def lambda_handler(event, context):
    http_method = event.get("httpMethod")
    path_parameters = event.get("pathParameters") or {}
    body = json.loads(event.get("body") or "{}") if event.get("body") else {}

    try:
        if http_method == "GET":
            if "target_id" in path_parameters:
                # Read single target
                response = table.get_item(Key={"target_id": path_parameters["target_id"]})
                item = response.get("Item")
                if not item:
                    return {"statusCode": 404, "body": json.dumps({"error": "Target not found"})}
                return {"statusCode": 200, "body": json.dumps(item)}
            else:
                # Read all targets
                response = table.scan()
                return {"statusCode": 200, "body": json.dumps(response.get("Items", []))}

        elif http_method == "POST":
            # Create target
            target_id = body.get("target_id")
            url = body.get("url")
            if not target_id or not url:
                return {"statusCode": 400, "body": json.dumps({"error": "target_id and url are required"})}
            
            table.put_item(Item={"target_id": target_id, "url": url, "status": "active"})
            return {"statusCode": 201, "body": json.dumps({"message": "Target created successfully", "target_id": target_id})}

        elif http_method == "PUT":
            # Update target
            target_id = path_parameters.get("target_id")
            status = body.get("status")
            if not target_id:
                return {"statusCode": 400, "body": json.dumps({"error": "target_id is required"})}

            table.update_item(
                Key={"target_id": target_id},
                UpdateExpression="SET #s = :status",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":status": status},
            )
            return {"statusCode": 200, "body": json.dumps({"message": "Target updated successfully"})}

        elif http_method == "DELETE":
            # Delete target
            target_id = path_parameters.get("target_id")
            if not target_id:
                return {"statusCode": 400, "body": json.dumps({"error": "target_id is required"})}

            table.delete_item(Key={"target_id": target_id})
            return {"statusCode": 200, "body": json.dumps({"message": "Target deleted successfully"})}

        return {"statusCode": 405, "body": json.dumps({"error": "Method not allowed"})}

    except ClientError as e:
        return {"statusCode": 500, "body": json.dumps({"error": e.response["Error"]["Message"]})}