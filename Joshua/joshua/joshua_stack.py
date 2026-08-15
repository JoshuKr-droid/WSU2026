# This file is the project infrastructure
# I add a bunch of comments to help me understand more

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_cloudwatch as cloudwatch,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda as lambda_,
)
from constructs import Construct

class JoshuaStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # The code that defines your stack goes here

        # https://docs.aws.amazon.com/lambda/latest/dg/lambda-cdk-tutorial.html
        # In class demonstration
        # Lambda function to check the health of a website

        # Creates lambda function and stores construct in variable fn
        fn = lambda_.Function(
            # Tells to put the lambda function in JoshuaStack
            self,
            # Construct ID for the lambda function
            "WebHealthLambda",
            # Execution environment for the lambda function
            runtime=lambda_.Runtime.PYTHON_3_14,
            # Finds the lambda_handler function in the webhealth.py file
            handler="webhealth.lambda_handler",
            # Tells that the code for the lambda function is in the joshua/resources directory
            code=lambda_.Code.from_asset("joshua/resources"),
            # lambda runs for a max of 30 seconds before timing out
            timeout=Duration.seconds(30),
        )
        # Destruction policy for the lambda function. If the stack is deleted, the lambda function will be deleted as well.
        fn.apply_removal_policy(RemovalPolicy.DESTROY)

        # Invokes lambda function every x minutes
        rule = events.Rule(
            self,
            "LambdaInvocationRule",
            schedule=events.Schedule.rate(Duration.minutes(30)),
        )
        # Tells to invoke the lambda function when the rule is triggered
        rule.add_target(targets.LambdaFunction(fn))
        # Destruction policy for the rule. If the stack is deleted, the rule will be deleted as well.
        rule.apply_removal_policy(RemovalPolicy.DESTROY)

        # CloudWatch dashboard for website health monitoring
        dashboard = cloudwatch.Dashboard(
            self,
            "WebHealthDashboard",
            dashboard_name="WebHealthMonitoring",
        )

        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Website Availability",
                left=[
                    cloudwatch.Metric(
                        namespace="WebHealth",
                        metric_name="AVAILABILITY_METRIC",
                        statistic="Average",
                        period=Duration.minutes(5),
                        dimensions_map={"URL": "https://www.westernsydney.edu.au/"},
                    )
                ],
            ),
            cloudwatch.GraphWidget(
                title="Website Latency",
                left=[
                    cloudwatch.Metric(
                        namespace="WebHealth",
                        metric_name="LATENCY_METRIC",
                        statistic="Average",
                        period=Duration.minutes(5),
                        dimensions_map={"URL": "https://www.westernsydney.edu.au/"},
                    )
                ],
            ),
        )