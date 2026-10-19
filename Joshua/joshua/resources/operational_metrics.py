import logging
import time
from collections.abc import Callable
from typing import TypeVar

import boto3


logger = logging.getLogger(__name__)
T = TypeVar("T")


def measure_dynamodb_operation(
    operation: str,
    access_type: str,
    action: Callable[[], T],
) -> T:
    started_at = time.perf_counter()
    try:
        return action()
    finally:
        duration_ms = (time.perf_counter() - started_at) * 1000
        try:
            boto3.client("cloudwatch").put_metric_data(
                Namespace="CrawlerOperations",
                MetricData=[
                    {
                        "MetricName": f"DynamoDB{access_type}Latency",
                        "Dimensions": [{"Name": "Operation", "Value": operation}],
                        "Unit": "Milliseconds",
                        "Value": duration_ms,
                    }
                ],
            )
        except Exception:
            logger.exception(
                "Could not publish DynamoDB %s latency for %s.",
                access_type.lower(),
                operation,
            )
