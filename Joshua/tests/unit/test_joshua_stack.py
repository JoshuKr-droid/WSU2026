# This file testst the project infrastructure

import aws_cdk as core
import aws_cdk.assertions as assertions

from joshua.joshua_stack import JoshuaStack

# example tests. To run these tests, uncomment this file along with the example
# resource in joshua/joshua_stack.py
def test_lambda_and_schedule_created():
    # Creates a CDK application and a stack
    app = core.App()
    stack = JoshuaStack(app, "joshua")
    # Gives you access to the synthesized CloudFormation template
    template = assertions.Template.from_stack(stack)

    # Expects cloudformation template to have 1 Lambda function, 1 EventBridge rule, and 2 alarms
    template.resource_count_is("AWS::Lambda::Function", 1)
    template.resource_count_is("AWS::Events::Rule", 1)
    template.resource_count_is("AWS::CloudWatch::Alarm", 2)

    # Finds the Lambda resource and make sure its Handler property is webhealth.lambda_handler."
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "webhealth.lambda_handler",
        },
    )

    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "ComparisonOperator": "LessThanThreshold",
            "Threshold": 0.9,
        },
    )

    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "ComparisonOperator": "GreaterThanThreshold",
            "Threshold": 2,
        },
    )

    # When AWS::Something::Something strings in CDK tests, think: "That's the CloudFormation name for the AWS resource I'm checking."
