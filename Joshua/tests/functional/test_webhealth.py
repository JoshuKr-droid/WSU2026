# This file contains the functional tests for the Beta stage of the pipeline.
# These tests check that the web health Lambda behaves correctly when given
# different website responses.

import importlib
from pathlib import Path

from urllib.error import URLError
from unittest.mock import Mock

import pytest


# Finds the folder containing the Lambda code.
RESOURCE_DIR = Path(__file__).resolve().parents[2] / "joshua" / "resources"

# The three websites monitored by the web health Lambda.
WEBSITE_URLS = (
    "https://www.westernsydney.edu.au/",
    "https://www.unsw.edu.au/",
    "https://www.sydney.edu.au/",
)


# Loads the webhealth Lambda code so the tests can run its lambda_handler function.
@pytest.fixture
def webhealth(monkeypatch):
    monkeypatch.syspath_prepend(str(RESOURCE_DIR))
    return importlib.import_module("webhealth")


# Stores the metrics that would normally be sent to CloudWatch.
# This allows us to check what the Lambda tried to publish without
# actually sending data to AWS CloudWatch.
@pytest.fixture
def published_metrics(webhealth, monkeypatch):
    metrics = []

    # Replaces the real boto3 CloudWatch client with a mock.
    monkeypatch.setattr(webhealth.boto3, "client", Mock())

    # Replaces putDataFunc with a function that stores the metric in a list.
    monkeypatch.setattr(
        webhealth.cw,
        "putDataFunc",
        lambda namespace, metric_name, url, value, unit: metrics.append(
            (namespace, metric_name, url, value, unit)
        ),
    )

    return metrics


# Creates a fake website response with the specified HTTP status code.
# This means the tests do not need to contact the real websites.
def response_with_status(status_code):
    response = Mock()

    # Makes the mock work with the "with" statement used by urlopen().
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)

    # Makes getcode() return the status code we provide.
    response.getcode.return_value = status_code

    return response


# Gets the URL and value for a specific metric from the published metrics.
# This makes it easier for the tests to check the results.
def metric_values(metrics, metric_name):
    return [
        (url, value)
        for _, name, url, value, _ in metrics
        if name == metric_name
    ]


# Test 1-4: Check that different HTTP responses produce the correct
# availability value.
#
# 200 = available
# 302 = available because redirects are treated as available
# 404 = unavailable
# 500 = unavailable
@pytest.mark.parametrize(
    ("status_code", "expected_availability"),
    [
        pytest.param(200, 1, id="success"),
        pytest.param(302, 1, id="redirect"),
        pytest.param(404, 0, id="client-error"),
        pytest.param(500, 0, id="server-error"),
    ],
)
def test_http_status_sets_expected_availability(
    webhealth, published_metrics, monkeypatch, status_code, expected_availability
):
    # Replaces the real website request with a fake response.
    monkeypatch.setattr(
        webhealth.urllib.request,
        "urlopen",
        Mock(return_value=response_with_status(status_code)),
    )

    # Run the Lambda using the fake website response.
    webhealth.lambda_handler({}, None)

    # Check that the expected availability value was published for all websites.
    assert metric_values(published_metrics, "AVAILABILITY_METRIC") == [
        (url, expected_availability) for url in WEBSITE_URLS
    ]


# Test 5: Check that the actual HTTP status code is published.
def test_actual_http_status_code_is_published(
    webhealth, published_metrics, monkeypatch
):
    # Use 418 as a test status code to make sure the actual response
    # code is being passed through to the metric.
    status_code = 418

    monkeypatch.setattr(
        webhealth.urllib.request,
        "urlopen",
        Mock(return_value=response_with_status(status_code)),
    )

    webhealth.lambda_handler({}, None)

    # Check that the status code was published for all three websites.
    assert metric_values(published_metrics, "HTTP_STATUS_CODE") == [
        (url, status_code) for url in WEBSITE_URLS
    ]


# Test 6: Check that the Lambda calculates and publishes website latency.
def test_request_latency_is_calculated_and_published(
    webhealth, published_metrics, monkeypatch
):
    monkeypatch.setattr(
        webhealth.urllib.request,
        "urlopen",
        Mock(return_value=response_with_status(200)),
    )

    # Provides fake start and end times so we can check the latency calculation.
    # For example, 12.5 - 10.0 = 2.5 seconds.
    monkeypatch.setattr(
        webhealth.time,
        "time",
        Mock(side_effect=[10.0, 12.5, 20.0, 21.0, 30.0, 30.25]),
    )

    webhealth.lambda_handler({}, None)

    # Check that the expected latency was published for each website.
    assert metric_values(published_metrics, "LATENCY_METRIC") == [
        (WEBSITE_URLS[0], 2.5),
        (WEBSITE_URLS[1], 1.0),
        (WEBSITE_URLS[2], 0.25),
    ]


# Test 7: Check that a website request failure is handled correctly.
def test_http_request_failure_publishes_zero_metrics(
    webhealth, published_metrics, monkeypatch
):
    # Simulates a connection failure when trying to access a website.
    monkeypatch.setattr(
        webhealth.urllib.request,
        "urlopen",
        Mock(side_effect=URLError("simulated connection failure")),
    )

    webhealth.lambda_handler({}, None)

    # When a request fails, all three metrics should be set to 0.
    assert metric_values(published_metrics, "AVAILABILITY_METRIC") == [
        (url, 0) for url in WEBSITE_URLS
    ]

    assert metric_values(published_metrics, "LATENCY_METRIC") == [
        (url, 0) for url in WEBSITE_URLS
    ]

    assert metric_values(published_metrics, "HTTP_STATUS_CODE") == [
        (url, 0) for url in WEBSITE_URLS
    ]


# Test 8: Check that all three websites are processed and all three metrics are published for each website.
def test_all_three_websites_publish_each_metric(
    webhealth, published_metrics, monkeypatch
):
    # Give each website a different fake response.
    responses = [
        response_with_status(200),
        response_with_status(302),
        response_with_status(503),
    ]

    # Return the fake responses in the same order as the websites.
    urlopen = Mock(side_effect=responses)

    monkeypatch.setattr(
        webhealth.urllib.request,
        "urlopen",
        urlopen,
    )

    webhealth.lambda_handler({}, None)

    # Check that all three website URLs were requested.
    assert [call.args[0] for call in urlopen.call_args_list] == list(WEBSITE_URLS)

    # Each website should publish 3 metrics:
    # availability, latency and HTTP status code.
    # 3 websites x 3 metrics = 9 metrics.
    assert len(published_metrics) == 9

    # Check that all three expected metric types were published.
    assert {
        metric_name for _, metric_name, _, _, _ in published_metrics
    } == {
        "AVAILABILITY_METRIC",
        "LATENCY_METRIC",
        "HTTP_STATUS_CODE",
    }

    # Check that metrics were published for all three websites.
    assert {
        url for _, _, url, _, _ in published_metrics
    } == set(WEBSITE_URLS)