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

# Infrastructure Unit Test 1: all four Lambda functions are synthesized.
def test_lambd_functions_are_created(template):
    template.resource_count_is("AWS::Lambda::Function", 4)

# Infrastructure Unit Test 2: the website monitor uses its expected entry point.
def test_web_health_lambda_handler(template):
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "webhealth.lambda_handler",
        },
    )


# Lambda creates its log group at runtime; CloudFormation must not recreate it.
def test_lambda_log_groups_are_not_managed_by_cloudformation():
    app = core.App(
        context={"@aws-cdk/aws-lambda:useCdkManagedLogGroup": False}
    )
    stack = JoshuaStack(app, "joshua")
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::Logs::LogGroup", 0)


# Infrastructure Unit Test 3: a scheduled EventBridge rule is synthesized.
def test_eventbridge_schedule_is_created(template):
    template.resource_count_is("AWS::Events::Rule", 1)

# Infrastructure Unit Test 4: the monitor schedule is every five minutes.
def test_schedule_runs_every_five_minutes(template):
    template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "ScheduleExpression": "rate(5 minutes)",
        },
    )


# Infrastructure Unit Test 5: scheduled invocations target the rollback-capable alias.
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


# Infrastructure Unit Test 6: target, alarm, and rollback history tables exist.
def test_dynamodb_tables_are_created(template):
    template.resource_count_is("AWS::DynamoDB::Table", 3)

# Infrastructure Unit Test 7: the alarm notification SNS topic is created.
def test_sns_notification_topic_is_created(template):
    template.resource_count_is("AWS::SNS::Topic", 1)

# Infrastructure Unit Test 8: nine website alarms and three Lambda alarms exist.
def test_twelve_alarms_are_created(template):
    template.resource_count_is("AWS::CloudWatch::Alarm", 12)


# Infrastructure Unit Test 9: missing invocations are treated as an alarm.
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

    # Infrastructure Unit Test 14: Lambda duration is measured in milliseconds,
    # so the 25-second threshold must be represented as 25,000.
def test_duration_alarm_threshold_is_twenty_five_seconds(template):
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "AlarmDescription": "Rollback trigger: Crawler processing time too high.",
            "MetricName": "Duration",
            "Threshold": 25_000,
            "ComparisonOperator": "GreaterThanThreshold",
            "EvaluationPeriods": 1,
            "Period": 60,
            "Statistic": "Average",
        },
    )


# Infrastructure Unit Test 10: the availability threshold is 90 percent.
def test_availability_alarm_threshold_is_ninety_percent(template):
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "ComparisonOperator": "LessThanThreshold",
            "Threshold": 0.9,
        },
    )

# Infrastructure Unit Test 11: the website latency threshold is two seconds.
def test_latency_alarm_threshold_is_two_seconds(template):
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "ComparisonOperator": "GreaterThanThreshold",
            "Threshold": 2,
        },
    )

# Infrastructure Unit Test 12: the CloudWatch monitoring dashboard exists.
def test_cloudwatch_dashboard_is_created(template):
    template.resource_count_is("AWS::CloudWatch::Dashboard", 1)


# Infrastructure Unit Test 13: deployment exposes the API base URL for clients.
def test_crawler_api_url_is_a_stack_output(template):
    template.has_output(
        "CrawlerApiUrl",
        {
            "Description": "Base URL for the public crawler targets REST API.",
        },
    )