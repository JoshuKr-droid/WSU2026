import importlib
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import boto3
from botocore.stub import Stubber


RESOURCE_DIR = Path(__file__).resolve().parents[2] / "joshua" / "resources"

WEBSITE_URLS = [
    "https://www.westernsydney.edu.au/",
    "https://www.unsw.edu.au/",
    "https://www.sydney.edu.au/",
]


def test_webhealth_publishes_metrics_to_cloudwatch(monkeypatch):
    # Provide dummy credentials so the test never needs real AWS credentials.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-2")

    # Import the actual application modules.
    monkeypatch.syspath_prepend(str(RESOURCE_DIR))
    importlib.invalidate_caches()

    webhealth = importlib.import_module("webhealth")
    webhealth = importlib.reload(webhealth)
    cw = webhealth.cw

    # Create a real Boto3 CloudWatch client with stubbed API responses.
    client = boto3.client("cloudwatch", region_name="ap-southeast-2")
    stubber = Stubber(client)

    # The crawler creates a client in webhealth.py and another in
    # CWPutData.py. Route both calls to the same stubbed client.
    monkeypatch.setattr(
        webhealth.boto3,
        "client",
        lambda service_name, **kwargs: client,
    )

    # Fake website responses; no external websites are contacted.
    responses = []

    for status_code in (200, 302, 503):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.getcode.return_value = status_code
        responses.append(response)

    monkeypatch.setattr(
        webhealth.urllib.request,
        "urlopen",
        Mock(side_effect=responses),
    )

    # Make latency deterministic for reliable assertions.
    monkeypatch.setattr(
        webhealth.time,
        "time",
        Mock(side_effect=[10.0, 10.5, 20.0, 21.0, 30.0, 32.0]),
    )

    expected_metrics = [
        ("AVAILABILITY_METRIC", WEBSITE_URLS[0], 1, "None"),
        ("LATENCY_METRIC", WEBSITE_URLS[0], 0.5, "Seconds"),
        ("HTTP_STATUS_CODE", WEBSITE_URLS[0], 200, "None"),
        ("AVAILABILITY_METRIC", WEBSITE_URLS[1], 1, "None"),
        ("LATENCY_METRIC", WEBSITE_URLS[1], 1.0, "Seconds"),
        ("HTTP_STATUS_CODE", WEBSITE_URLS[1], 302, "None"),
        ("AVAILABILITY_METRIC", WEBSITE_URLS[2], 0, "None"),
        ("LATENCY_METRIC", WEBSITE_URLS[2], 2.0, "Seconds"),
        ("HTTP_STATUS_CODE", WEBSITE_URLS[2], 503, "None"),
    ]

    # Stub and validate every CloudWatch API request.
    for metric_name, url, value, unit in expected_metrics:
        stubber.add_response(
            "put_metric_data",
            {},
            {
                "Namespace": "WebHealth",
                "MetricData": [
                    {
                        "MetricName": metric_name,
                        "Dimensions": [
                            {"Name": "URL", "Value": url}
                        ],
                        "Unit": unit,
                        "Value": float(value),
                    }
                ],
            },
        )

    with stubber:
        result = webhealth.lambda_handler({}, None)
        stubber.assert_no_pending_responses()

    assert result == {
        "statusCode": 200,
        "body": "Metric publishing complete",
    }