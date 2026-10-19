import importlib
from pathlib import Path
from unittest.mock import Mock

import pytest


RESOURCE_DIR = Path(__file__).resolve().parents[2] / "joshua" / "resources"


@pytest.fixture
def webhealth(monkeypatch):
    monkeypatch.setenv("CRAWLER_TARGETS_TABLE", "CrawlerTargets")
    monkeypatch.syspath_prepend(str(RESOURCE_DIR))
    module = importlib.import_module("webhealth")
    metrics = importlib.import_module("operational_metrics")
    monkeypatch.setattr(module.boto3, "resource", Mock())
    monkeypatch.setattr(metrics.boto3, "client", Mock())
    return module, metrics


# Applied Project Functional Test 4: target scans paginate and record read latency.
def test_load_active_targets_reads_all_pages_and_records_read_latency(
    webhealth,
):
    module, metrics = webhealth
    table = Mock()
    module.boto3.resource.return_value.Table.return_value = table
    table.scan.side_effect = [
        {
            "Items": [
                {
                    "target_id": "active-1",
                    "url": "https://one.example",
                    "status": "active",
                },
                {
                    "target_id": "paused-1",
                    "url": "https://paused.example",
                    "status": "paused",
                },
            ],
            "LastEvaluatedKey": {"target_id": "paused-1"},
        },
        {
            "Items": [
                {
                    "target_id": "active-2",
                    "url": "https://two.example",
                    "status": "active",
                },
            ],
        },
    ]

    assert module.load_active_targets() == [
        "https://one.example",
        "https://two.example",
    ]
    assert table.scan.call_count == 2
    assert table.scan.call_args_list[1].kwargs == {
        "ExclusiveStartKey": {"target_id": "paused-1"}
    }
    metric_data = metrics.boto3.client.return_value.put_metric_data.call_args.kwargs
    assert metric_data["Namespace"] == "CrawlerOperations"
    assert metric_data["MetricData"][0]["MetricName"] == "DynamoDBReadLatency"
    assert metric_data["MetricData"][0]["Dimensions"] == [
        {"Name": "Operation", "Value": "list_crawl_targets"}
    ]
    assert metric_data["MetricData"][0]["Unit"] == "Milliseconds"
    assert metric_data["MetricData"][0]["Value"] >= 0


# Applied Project Functional Test 5: crawler checks active database-managed targets.
def test_webhealth_checks_only_database_targets(webhealth, monkeypatch):
    module, _ = webhealth
    targets = ["https://configured.example/path"]
    monkeypatch.setattr(module, "load_active_targets", lambda: targets)
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.getcode.return_value = 200
    urlopen = Mock(return_value=response)
    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    published_metrics = []
    monkeypatch.setattr(
        module.cw,
        "putDataFunc",
        lambda namespace, name, url, value, unit: published_metrics.append(
            (name, url, value, unit)
        ),
    )

    result = module.lambda_handler({}, None)

    assert result["statusCode"] == 200
    assert urlopen.call_args_list[0].args[0] == targets[0]
    assert len(published_metrics) == 3
    assert {metric[1] for metric in published_metrics} == set(targets)


# Applied Project Functional Test 6: an empty table does not use a fixed URL list.
def test_empty_target_table_does_not_request_hard_coded_sites(webhealth, monkeypatch):
    module, _ = webhealth
    monkeypatch.setattr(module, "load_active_targets", lambda: [])
    urlopen = Mock()
    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    metric_publisher = Mock()
    monkeypatch.setattr(module.cw, "putDataFunc", metric_publisher)

    result = module.lambda_handler({}, None)

    assert result["statusCode"] == 200
    assert urlopen.call_count == 0
    metric_publisher.assert_not_called()


# Applied Project Functional Test 7: target creation emits write-latency metrics.
def test_target_creation_publishes_dynamodb_write_latency(
    webhealth, monkeypatch
):
    module, metrics = webhealth
    crud = importlib.import_module("crawler_crud")
    table = Mock()
    monkeypatch.setattr(crud, "table", table)
    result = crud.lambda_handler(
        {
            "httpMethod": "POST",
            "pathParameters": None,
            "body": '{"target_id":"site-1","url":"https://example.com"}',
        },
        None,
    )

    assert result["statusCode"] == 201
    table.put_item.assert_called_once()
    metric_data = metrics.boto3.client.return_value.put_metric_data.call_args.kwargs
    assert metric_data["MetricData"][0]["MetricName"] == "DynamoDBWriteLatency"
    assert metric_data["MetricData"][0]["Dimensions"] == [
        {"Name": "Operation", "Value": "create_target"}
    ]
