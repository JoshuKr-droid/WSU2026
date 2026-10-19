import os
import urllib.request
import uuid

import boto3
import pytest


AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
RUN_AWS_INTEGRATION_TESTS = (
    os.getenv("RUN_AWS_INTEGRATION_TESTS", "").lower() == "true"
)
AWS_REGION = os.getenv("AWS_DEFAULT_REGION") or os.getenv("AWS_REGION") or "ap-southeast-2"
_boto3_client = boto3.client
_boto3_resource = boto3.resource


def require_integration_environment(*required_variables):
    if RUN_AWS_INTEGRATION_TESTS:
        missing = [
            name for name in required_variables if not os.getenv(name)
        ]
        if missing:
            raise RuntimeError(
                "AWS integration tests require environment variables: "
                + ", ".join(missing)
            )
        return

    if not AWS_ENDPOINT_URL:
        pytest.skip(
            "Set AWS_ENDPOINT_URL for LocalStack or "
            "RUN_AWS_INTEGRATION_TESTS=true for deployed AWS resources."
        )

    try:
        with urllib.request.urlopen(
            f"{AWS_ENDPOINT_URL}/_localstack/health",
            timeout=3,
        ) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"LocalStack health check returned {response.status}"
                )
    except Exception as error:
        pytest.skip(f"LocalStack is not available at {AWS_ENDPOINT_URL}: {error}")


def configure_boto3(monkeypatch):
    def client(service_name, **kwargs):
        kwargs.setdefault("region_name", AWS_REGION)
        if AWS_ENDPOINT_URL:
            kwargs.setdefault("endpoint_url", AWS_ENDPOINT_URL)
            kwargs.setdefault("aws_access_key_id", "test")
            kwargs.setdefault("aws_secret_access_key", "test")
        return _boto3_client(service_name, **kwargs)

    def resource(service_name, **kwargs):
        kwargs.setdefault("region_name", AWS_REGION)
        if AWS_ENDPOINT_URL:
            kwargs.setdefault("endpoint_url", AWS_ENDPOINT_URL)
            kwargs.setdefault("aws_access_key_id", "test")
            kwargs.setdefault("aws_secret_access_key", "test")
        return _boto3_resource(service_name, **kwargs)

    monkeypatch.setattr(boto3, "client", client)
    monkeypatch.setattr(boto3, "resource", resource)


def aws_client(service_name):
    kwargs = {"region_name": AWS_REGION}
    if AWS_ENDPOINT_URL:
        kwargs.update(
            endpoint_url=AWS_ENDPOINT_URL,
            aws_access_key_id="test",
            aws_secret_access_key="test",
        )
    return _boto3_client(service_name, **kwargs)


def aws_resource(service_name):
    kwargs = {"region_name": AWS_REGION}
    if AWS_ENDPOINT_URL:
        kwargs.update(
            endpoint_url=AWS_ENDPOINT_URL,
            aws_access_key_id="test",
            aws_secret_access_key="test",
        )
    return _boto3_resource(service_name, **kwargs)


def create_test_table(table_name, partition_key, sort_key=None):
    key_schema = [{"AttributeName": partition_key, "KeyType": "HASH"}]
    attributes = [{"AttributeName": partition_key, "AttributeType": "S"}]
    if sort_key:
        key_schema.append(
            {"AttributeName": sort_key, "KeyType": "RANGE"}
        )
        attributes.append({"AttributeName": sort_key, "AttributeType": "S"})
    aws_client("dynamodb").create_table(
        TableName=table_name,
        KeySchema=key_schema,
        AttributeDefinitions=attributes,
        BillingMode="PAY_PER_REQUEST",
    )
    aws_client("dynamodb").get_waiter("table_exists").wait(TableName=table_name)


def create_targets_table(table_name):
    aws_client("dynamodb").create_table(
        TableName=table_name,
        KeySchema=[{"AttributeName": "target_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "target_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    aws_client("dynamodb").get_waiter("table_exists").wait(TableName=table_name)


def unique_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex}"
