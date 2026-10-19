import importlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError


RESOURCE_DIR = Path(__file__).resolve().parents[2] / "joshua" / "resources"


@pytest.fixture
def crawler_crud(monkeypatch):
    monkeypatch.setenv("CRAWLER_TARGETS_TABLE", "CrawlerTargets")
    monkeypatch.syspath_prepend(str(RESOURCE_DIR))
    module = importlib.import_module("crawler_crud")
    monkeypatch.setattr(module, "table", Mock())
    metrics = importlib.import_module("operational_metrics")
    monkeypatch.setattr(metrics.boto3, "client", Mock())
    return module


def api_event(method, body=None, target_id=None):
    return {
        "httpMethod": method,
        "pathParameters": {"target_id": target_id} if target_id else None,
        "body": json.dumps(body) if body is not None else None,
    }


# Applied Project Unit Test 3: malformed JSON must return a client error
# without attempting any DynamoDB operation.
def test_malformed_json_returns_bad_request_without_database_access(crawler_crud):
    result = crawler_crud.lambda_handler(
        {"httpMethod": "POST", "body": "{not-json", "pathParameters": None},
        None,
    )

    assert result["statusCode"] == 400
    crawler_crud.table.put_item.assert_not_called()


# Applied Project Unit Test 4: a duplicate create must map DynamoDB's
# conditional-write failure to HTTP 409 Conflict.
def test_duplicate_target_returns_conflict(crawler_crud):
    crawler_crud.table.put_item.side_effect = ClientError(
        {
            "Error": {
                "Code": "ConditionalCheckFailedException",
                "Message": "Target already exists.",
            }
        },
        "PutItem",
    )

    result = crawler_crud.lambda_handler(
        api_event(
            "POST",
            {"target_id": "site-1", "url": "https://example.com"},
        ),
        None,
    )

    assert result["statusCode"] == 409
    assert json.loads(result["body"])["error"] == (
        "A target with this target_id already exists."
    )


# Applied Project Unit Test 5: an update with an invalid status must be
# rejected before DynamoDB is called.
def test_invalid_status_is_rejected_without_database_access(crawler_crud):
    result = crawler_crud.lambda_handler(
        api_event("PUT", {"status": "deleted"}, "site-1"),
        None,
    )

    assert result["statusCode"] == 400
    crawler_crud.table.update_item.assert_not_called()
