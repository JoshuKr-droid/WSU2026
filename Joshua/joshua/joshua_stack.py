# This file is the project infrastructure
# I add a bunch of comments to help me understand more

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cloudwatch_actions,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    aws_dynamodb as dynamodb,
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

        # Grants the lambda function permission to put metric data to CloudWatch
        # (May be able to be put into the lambda function itself, but I don't know how to do that yet.)
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
            )
        )

        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_dynamodb/Table.html
        alarm_log_table = dynamodb.Table(
            self,
            "AlarmLogTable",
            partition_key=dynamodb.Attribute(
                name="alarm_name",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="state_change_time",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # This passes the DynamoDB table name into the Lambda through an environment variable.
        alarm_logger = lambda_.Function(
            self,
            "AlarmLoggerLambda",
            runtime=lambda_.Runtime.PYTHON_3_14,
            handler="alarm_logger.lambda_handler",
            code=lambda_.Code.from_asset("joshua/resources"),
            environment={"ALARM_LOG_TABLE": alarm_log_table.table_name},
        )

        # Gives your Lambda permission to write items into the table.
        alarm_log_table.grant_write_data(alarm_logger)

        # Invokes lambda function every x minutes
        rule = events.Rule(
            self,
            "LambdaInvocationRule",
            schedule=events.Schedule.rate(Duration.minutes(2)),
        )

        # Tells to invoke the lambda function when the rule is triggered
        rule.add_target(targets.LambdaFunction(fn))

        # Destruction policy for the rule. If the stack is deleted, the rule will be deleted as well.
        rule.apply_removal_policy(RemovalPolicy.DESTROY)

        # Websites being monitored.
        # These URLs must match the URLs used in webhealth.py.
        website_urls = [
            "https://www.westernsydney.edu.au/",
            "https://www.unsw.edu.au/",
            "https://www.sydney.edu.au/",
        ]

        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_cloudwatch/Metric.html
        # Creates CloudWatch metrics for each website.
        # The URL dimension allows CloudWatch to distinguish between the different websites.

        availability_metrics = []
        latency_metrics = []
        http_status_code_metrics = []

        for website_url in website_urls:

            # Creates an availability metric for the current website.
            availability_metrics.append(
                cloudwatch.Metric(
                    namespace="WebHealth",
                    metric_name="AVAILABILITY_METRIC",
                    statistic="Average",  # I probably shouldn't use average.
                    period=Duration.minutes(5),
                    dimensions_map={"URL": website_url},
                )
            )

            # Creates a latency metric for the current website.
            latency_metrics.append(
                cloudwatch.Metric(
                    namespace="WebHealth",
                    metric_name="LATENCY_METRIC",
                    statistic="Average",  # I probably shouldn't use average.
                    period=Duration.minutes(5),
                    dimensions_map={"URL": website_url},
                )
            )

            # Creates an HTTP status code metric for the current website.
            http_status_code_metrics.append(
                cloudwatch.Metric(
                    namespace="WebHealth",
                    metric_name="HTTP_STATUS_CODE",
                    statistic="Average",  # I probably shouldn't use average.
                    period=Duration.minutes(5),
                    dimensions_map={"URL": website_url},
                )
            )

        ## Notification service to notify ourselves of any significant change in our metric

        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_sns.Topic.html
        topic = sns.Topic(self, "AlarmNotifications")

        # When an alarm is triggered, an email will be sent to the specified email address.
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_sns_subscriptions.EmailSubscription.html
        topic.add_subscription(
            subscriptions.EmailSubscription("22195904@student.westernsydney.edu.au")
        )

        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_sns_subscriptions.LambdaSubscription.html
        # When an alarm is triggered, the lambda function will be invoked. This can be used to perform any additional actions when an alarm is triggered.
        topic.add_subscription(
            subscriptions.LambdaSubscription(alarm_logger)
        )

        alarm_action = cloudwatch_actions.SnsAction(topic)

        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_cloudwatch/Alarm.html
        # Creates alarms for each website.
        # Each website has an availability, latency and HTTP status code alarm.

        for i, website_url in enumerate(website_urls):

            # Creates an alarm for website availability metric.
            # If the availability drops below 90%, the alarm will be triggered.
            availabilityAlarm = cloudwatch.Alarm(
                self,
                f"WebsiteAvailabilityAlarm{i}",
                alarm_name=f"WebsiteAvailabilityAlarm-{i}",
                metric=availability_metrics[i],
                threshold=0.9,
                evaluation_periods=2,
                comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
                treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
                alarm_description=f"Alarm when {website_url} availability drops below 90%.",
            )

            # Destruction policy for the alarm.
            # If the stack is deleted, the alarm will be deleted as well.
            availabilityAlarm.apply_removal_policy(RemovalPolicy.DESTROY)

            # When the alarm is triggered, the SNS topic will be notified.
            # This sends an email and invokes the alarm logger Lambda.
            availabilityAlarm.add_alarm_action(alarm_action)


            # Creates an alarm for website latency metric.
            # If the latency exceeds 2 seconds, the alarm will be triggered.
            latencyAlarm = cloudwatch.Alarm(
                self,
                f"WebsiteLatencyAlarm{i}",
                alarm_name=f"WebsiteLatencyAlarm-{i}",
                metric=latency_metrics[i],
                threshold=2,
                evaluation_periods=2,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
                treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
                alarm_description=f"Alarm when {website_url} latency exceeds 2 seconds.",
            )

            # Destruction policy for the alarm.
            # If the stack is deleted, the alarm will be deleted as well.
            latencyAlarm.apply_removal_policy(RemovalPolicy.DESTROY)

            # When the alarm is triggered, the SNS topic will be notified.
            # This sends an email and invokes the alarm logger Lambda.
            latencyAlarm.add_alarm_action(alarm_action)


            # Creates an alarm for HTTP status codes (4xx and 5xx).
            # If the HTTP status code is greater than 400, the alarm will be triggered.
            httpStatusAlarm = cloudwatch.Alarm(
                self,
                f"WebsiteHttpStatusAlarm{i}",
                alarm_name=f"WebsiteHttpStatusAlarm-{i}",
                metric=http_status_code_metrics[i],
                threshold=400,
                evaluation_periods=2,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
                treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
                alarm_description=f"Alarm when {website_url} returns an HTTP status code greater than 400.",
            )

            # Destruction policy for the alarm.
            # If the stack is deleted, the alarm will be deleted as well.
            httpStatusAlarm.apply_removal_policy(RemovalPolicy.DESTROY)

            # When the alarm is triggered, the SNS topic will be notified.
            # This sends an email and invokes the alarm logger Lambda.
            httpStatusAlarm.add_alarm_action(alarm_action)


        # CloudWatch dashboard for website health monitoring
        dashboard = cloudwatch.Dashboard(
            self,
            "WebHealthDashboard",
            dashboard_name="WebHealthMonitoring",
        )

        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_cloudwatch/README.html#dashboards
        # GraphWidget can display multiple metrics on the same graph.
        # Each metric has a URL dimension, allowing all three websites to be displayed separately.
        dashboard.add_widgets(
            # Creates a graph for availability metrics for all three websites.
            cloudwatch.GraphWidget(
                title="Website Availability",
                left=availability_metrics,
            ),

            # Creates a graph for latency metrics for all three websites.
            cloudwatch.GraphWidget(
                title="Website Latency",
                left=latency_metrics,
            ),

            # Creates a graph for HTTP status code metrics for all three websites.
            cloudwatch.GraphWidget(
                title="HTTP Status Codes",
                left=http_status_code_metrics,
            ),
        )

        # I may have missed some info on topics/ alarm action / subscriptions. Though I'm not too sure.

        # Logging alarm information in DynamoDB database

        # Create dynamoDB, but pass it into the lambda function so it can write into the database?