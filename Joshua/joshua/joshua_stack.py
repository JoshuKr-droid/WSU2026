# This file is the project infrastructure
# I add a bunch of comments to help me understand more

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_cloudwatch as cloudwatch,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
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

        # Grants the lambda function permission to put metric data to CloudWatch (May be able to be put into the lambda function itself, but I don't know how to do that yet.)
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
            )
        )

        # Invokes lambda function every x minutes
        rule = events.Rule(
            self,
            "LambdaInvocationRule",
            schedule=events.Schedule.rate(Duration.minutes(5)),
        )
        # Tells to invoke the lambda function when the rule is triggered
        rule.add_target(targets.LambdaFunction(fn))
        # Destruction policy for the rule. If the stack is deleted, the rule will be deleted as well.
        rule.apply_removal_policy(RemovalPolicy.DESTROY)

        website_url = "https://www.westernsydney.edu.au/"

        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_cloudwatch/Alarm.html
        availability_metric = cloudwatch.Metric(
            namespace="WebHealth",
            metric_name="AVAILABILITY_METRIC",
            statistic="Average", # I probably shouldn't use average.
            period=Duration.minutes(5),
            dimensions_map={"URL": website_url},
        )
        latency_metric = cloudwatch.Metric(
            namespace="WebHealth",
            metric_name="LATENCY_METRIC",
            statistic="Average", # I probably shouldn't use average.
            period=Duration.minutes(5),
            dimensions_map={"URL": website_url},
        )
        http_status_code_metric = cloudwatch.Metric(
            namespace="WebHealth",
            metric_name="HTTP_STATUS_CODE",
            statistic="Average", # I probably shouldn't use average.
            period=Duration.minutes(5),
            dimensions_map={"URL": website_url},
        )

        # Creates an alarm for website availability metric. If the availability drops below 90%, the alarm will be triggered.
        cloudwatch.Alarm(
            self,
            "WebsiteAvailabilityAlarm",
            alarm_name="WebsiteAvailabilityAlarm",
            metric=availability_metric,
            threshold=0.9,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
            alarm_description="Alarm when the site availability drops below 90%.",
        )

        # Creates an alarm for website latency metric. If the latency exceeds 2 seconds, the alarm will be triggered.
        cloudwatch.Alarm(
            self,
            "WebsiteLatencyAlarm",
            alarm_name="WebsiteLatencyAlarm",
            metric=latency_metric,
            threshold=2,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
            alarm_description="Alarm when the site latency exceeds 2 seconds.",
        )

        # Create alarm for HTTP status codes (4xx and 5xx)
        cloudwatch.Alarm(
            self,
            "WebsiteHttpStatusAlarm",
            alarm_name="WebsiteHttpStatusAlarm",
            metric=http_status_code_metric,
            threshold=400,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
            alarm_description="Alarm when the site returns 4xx or 5xx HTTP status codes.",
        )

        # CloudWatch dashboard for website health monitoring
        dashboard = cloudwatch.Dashboard(
            self,
            "WebHealthDashboard",
            dashboard_name="WebHealthMonitoring",
        )

        #https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_cloudwatch/README.html#dashboards
        dashboard.add_widgets(
            # Creates a graph for availibility metric
            cloudwatch.GraphWidget(
                title="Website Availability",
                left=[availability_metric],
            ),
            # Creates a graph for latency metric
            cloudwatch.GraphWidget(
                title="Website Latency",
                left=[latency_metric],
            ),
            # Creates a graph for Http status codes metric
            cloudwatch.GraphWidget(
                title="HTTP Status Codes",
                left=[http_status_code_metric],
            ),
        )