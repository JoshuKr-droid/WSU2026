import importlib
from pathlib import Path
from unittest.mock import Mock

import pytest


RESOURCE_DIR = Path(__file__).resolve().parents[2] / "joshua" / "resources"


@pytest.fixture
def operational_metrics(monkeypatch):
    monkeypatch.syspath_prepend(str(RESOURCE_DIR))
    return importlib.import_module("operational_metrics")


def test_dynamodb_operation_publishes_elapsed_read_time(
    monkeypatch, operational_metrics
):
    clock = Mock(side_effect=[10.0, 10.025])
    cloudwatch = Mock()
    monkeypatch.setattr(operational_metrics.time, "perf_counter", clock)
    monkeypatch.setattr(
        operational_metrics.boto3,
        "client",
        Mock(return_value=cloudwatch),
    )
    action = Mock(return_value={"Items": []})

    result = operational_metrics.measure_dynamodb_operation(
        "list_targets",
        "Read",
        action,
    )

    assert result == {"Items": []}
    cloudwatch.put_metric_data.assert_called_once()
    metric = cloudwatch.put_metric_data.call_args.kwargs["MetricData"][0]
    assert metric["MetricName"] == "DynamoDBReadLatency"
    assert metric["Dimensions"] == [
        {"Name": "Operation", "Value": "list_targets"}
    ]
    assert metric["Unit"] == "Milliseconds"
    assert metric["Value"] == pytest.approx(25.0)


def test_dynamodb_operation_publishes_elapsed_write_time(
    monkeypatch, operational_metrics
):
    clock = Mock(side_effect=[20.0, 20.012])
    cloudwatch = Mock()
    monkeypatch.setattr(operational_metrics.time, "perf_counter", clock)
    monkeypatch.setattr(
        operational_metrics.boto3,
        "client",
        Mock(return_value=cloudwatch),
    )

    assert operational_metrics.measure_dynamodb_operation(
        "create_target",
        "Write",
        lambda: "created",
    ) == "created"

    metric = cloudwatch.put_metric_data.call_args.kwargs["MetricData"][0]
    assert metric["MetricName"] == "DynamoDBWriteLatency"
    assert metric["Dimensions"] == [
        {"Name": "Operation", "Value": "create_target"}
    ]
    assert metric["Unit"] == "Milliseconds"
    assert metric["Value"] == pytest.approx(12.0)
