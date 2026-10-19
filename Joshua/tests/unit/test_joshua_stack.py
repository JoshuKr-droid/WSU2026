# This file has the unit tests needed for Alpha stage of the pipeline. 
# The unit tests are run after the synth step in the pipeline

import json

import aws_cdk as core
import aws_cdk.assertions as assertions
import pytest

from joshua.joshua_stack import JoshuaStack

# Fixture used to create the CDK stack for each test.
@pytest.fixture
def template():
    app = core.App()
    stack = JoshuaStack(app, "joshua")
    return assertions.Template.from_stack(stack)

# Test 1: Check that all Lambda functions are created (Web health, alarm logger, and rollback handler).
def test_lambd_functions_are_created(template):
    template.resource_count_is("AWS::Lambda::Function", 4)

# Test 2: Check that the web health Lambda uses the correct handler.
def test_web_health_lambda_handler(template):
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "webhealth.lambda_handler",
        },
    )

# Test 3: Check that an EventBridge rule is created to trigger the web health Lambda.
def test_eventbridge_schedule_is_created(template):
    template.resource_count_is("AWS::Events::Rule", 1)

# Test 4: Check that the Lambda is scheduled to run every 5 minutes
def test_schedule_runs_every_five_minutes(template):
    template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "ScheduleExpression": "rate(5 minutes)",
        },
    )


def test_schedule_invokes_live_alias(template):
    resources = template.to_json()["Resources"]
    alias_logical_id = next(
        logical_id
        for logical_id, resource in resources.items()
        if resource["Type"] == "AWS::Lambda::Alias"
        and resource["Properties"]["Name"] == "Live"
    )
    rule = next(
        resource
        for resource in resources.values()
        if resource["Type"] == "AWS::Events::Rule"
    )

    assert alias_logical_id in json.dumps(rule["Properties"]["Targets"])


# Test 5: Check that the DynamoDB tables for alarm logging and rollback history are created
def test_dynamodb_tables_are_created(template):
    template.resource_count_is("AWS::DynamoDB::Table", 3)

# Test 6: Check that the SNS topic used for alarm notifications is created.
def test_sns_notification_topic_is_created(template):
    template.resource_count_is("AWS::SNS::Topic", 1)

# Test 7: Check that all 12 CloudWatch alarms are created (9 website alarms + 3 crawler operational alarms).
def test_twelve_alarms_are_created(template):
    template.resource_count_is("AWS::CloudWatch::Alarm", 12)


def test_invocation_alarm_detects_ten_minutes_without_invocations(template):
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "AlarmDescription": (
                "Rollback trigger: No crawler invocations in the last 10 minutes."
            ),
            "MetricName": "Invocations",
            "Threshold": 1,
            "ComparisonOperator": "LessThanThreshold",
            "EvaluationPeriods": 2,
            "DatapointsToAlarm": 2,
            "TreatMissingData": "breaching",
        },
    )

# Test 8: Check that the availability alarm triggers below 90%.
def test_availability_alarm_threshold_is_ninety_percent(template):
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "ComparisonOperator": "LessThanThreshold",
            "Threshold": 0.9,
        },
    )

# Test 9: Check that the latency alarm triggers above 2 seconds.
def test_latency_alarm_threshold_is_two_seconds(template):
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "ComparisonOperator": "GreaterThanThreshold",
            "Threshold": 2,
        },
    )

# Test 10: Check that the CloudWatch monitoring dashboard is created
def test_cloudwatch_dashboard_is_created(template):
    template.resource_count_is("AWS::CloudWatch::Dashboard", 1)