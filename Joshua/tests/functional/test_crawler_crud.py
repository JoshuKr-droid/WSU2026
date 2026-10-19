import importlib
import json
from pathlib import Path

import pytest
from botocore.exceptions import ClientError


RESOURCE_DIR = Path(__file__).resolve().parents[2] / "joshua" / "resources"


class InMemoryTargetsTable:
    """Stateful DynamoDB stand-in for API-level CRUD tests."""

    def __init__(self):
        self.items = {}

    def put_item(self, *, Item, ConditionExpression):
        target_id = Item["target_id"]
        if target_id in self.items:
            raise self._conditional_failure("PutItem")
        self.items[target_id] = dict(Item)
        return {}

    def get_item(self, *, Key):
        item = self.items.get(Key["target_id"])
        return {"Item": dict(item)} if item else {}

    def scan(self, **kwargs):
        return {"Items": [dict(item) for item in self.items.values()]}

    def update_item(
        self,
        *,
        Key,
        ExpressionAttributeNames,
        ExpressionAttributeValues,
        **kwargs,
    ):
        target_id = Key["target_id"]
        if target_id not in self.items:
            raise self._conditional_failure("UpdateItem")
        for expression_name, field_name in ExpressionAttributeNames.items():
            value_name = f":{expression_name[1:]}"
            self.items[target_id][field_name] = ExpressionAttributeValues[value_name]
        return {"Attributes": dict(self.items[target_id])}

    def delete_item(self, *, Key, **kwargs):
        target_id = Key["target_id"]
        if target_id not in self.items:
            raise self._conditional_failure("DeleteItem")
        return {"Attributes": self.items.pop(target_id)}

    @staticmethod
    def _conditional_failure(operation):
        return ClientError(
            {
                "Error": {
                    "Code": "ConditionalCheckFailedException",
                    "Message": "Target does not exist.",
                }
            },
            operation,
        )


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("CRAWLER_TARGETS_TABLE", "CrawlerTargets")
    monkeypatch.syspath_prepend(str(RESOURCE_DIR))
    module = importlib.import_module("crawler_crud")
    monkeypatch.setattr(module, "table", InMemoryTargetsTable())
    metrics = importlib.import_module("operational_metrics")
    monkeypatch.setattr(metrics.boto3, "client", lambda *_args, **_kwargs: _NoopCloudWatch())
    return module


class _NoopCloudWatch:
    def put_metric_data(self, **kwargs):
        return {}


def api_event(method, body=None, target_id=None):
    return {
        "httpMethod": method,
        "pathParameters": {"target_id": target_id} if target_id else None,
        "body": json.dumps(body) if body is not None else None,
    }


def response_body(result):
    return json.loads(result["body"])


# Applied Project Functional Test 1: exercises the public handler's create
# and read routes and verifies the created target's initial active status.
def test_create_target_then_read_it(api):
    created = api.lambda_handler(
        api_event(
            "POST",
            {"target_id": "site-1", "url": "https://example.com"},
        ),
        None,
    )
    fetched = api.lambda_handler(api_event("GET", target_id="site-1"), None)

    assert created["statusCode"] == 201
    assert response_body(created) == {
        "target_id": "site-1",
        "url": "https://example.com",
        "status": "active",
    }
    assert fetched["statusCode"] == 200
    assert response_body(fetched) == response_body(created)


# Applied Project Functional Test 2: creates a target, updates both allowed
# fields through the API handler, and verifies the returned updated item.
def test_update_target_url_and_status(api):
    api.lambda_handler(
        api_event(
            "POST",
            {"target_id": "site-2", "url": "https://old.example"},
        ),
        None,
    )

    updated = api.lambda_handler(
        api_event(
            "PUT",
            {"url": "https://new.example/path", "status": "paused"},
            "site-2",
        ),
        None,
    )

    assert updated["statusCode"] == 200
    assert response_body(updated) == {
        "target_id": "site-2",
        "url": "https://new.example/path",
        "status": "paused",
    }


# Applied Project Functional Test 3: creates then deletes a target, checks
# the deleted record, and confirms subsequent reads return 404.
def test_delete_target_then_confirm_not_found(api):
    api.lambda_handler(
        api_event(
            "POST",
            {"target_id": "site-3", "url": "https://delete.example"},
        ),
        None,
    )

    deleted = api.lambda_handler(
        api_event("DELETE", target_id="site-3"),
        None,
    )
    fetched = api.lambda_handler(api_event("GET", target_id="site-3"), None)

    assert deleted["statusCode"] == 200
    assert response_body(deleted)["target_id"] == "site-3"
    assert fetched["statusCode"] == 404
