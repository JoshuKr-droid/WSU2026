# This file is the project infrastructure
# I add a bunch of comments to help me understand more

from aws_cdk import (
    CfnOutput,
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

        crawler_targets_table = dynamodb.Table(
            self,
            "CrawlerTargetsTable",
            partition_key=dynamodb.Attribute(
                name="target_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True,
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )
        self.crawler_targets_table = crawler_targets_table
        self.crawler_targets_table_name_output = CfnOutput(
            self,
            "CrawlerTargetsTableName",
            value=crawler_targets_table.table_name,
        )

        # Creates lambda function and stores construct in variable fn
        fn = lambda_.Function(
            # Tells to put the lambda function in JoshuaStack
            self,
            # Construct ID for the lambda function
            "WebHealthLambda",
            # Execution environment for the lambda function
            runtime=lambda_.Runtime.PYTHON_3_14,
            function_name=f"{construct_id.lower()}-webhealth",
            # Finds the lambda_handler function in the webhealth.py file
            handler="webhealth.lambda_handler",
            # Tells that the code for the lambda function is in the joshua/resources directory
            code=lambda_.Code.from_asset("joshua/resources"),
            environment={
                "CRAWLER_TARGETS_TABLE": crawler_targets_table.table_name,
            },
            # lambda runs for a max of 30 seconds before timing out
            timeout=Duration.seconds(30),
        )
        crawler_targets_table.grant_read_data(fn)

        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_lambda/Alias.html
        # Creates an alias for the lambda function. This allows us to have multiple versions of the lambda function and switch between them easily.
        version = fn.current_version
        alias = lambda_.Alias(
            self,
            "WebHealthLambdaAlias",
            alias_name="Live",
            version=version,
        )
        self.web_health_alias = alias
        self.web_health_alias_arn_output = CfnOutput(
            self,
            "WebHealthAliasArn",
            value=alias.function_arn,
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
        self.alarm_log_table = alarm_log_table
        self.alarm_log_table_name_output = CfnOutput(
            self,
            "AlarmLogTableName",
            value=alarm_log_table.table_name,
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

        # ==========================================
        # WEEK 11: Custom Rollback Infrastructure (Replaces CodeDeploy)
        # ==========================================
        
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_dynamodb/Table.html
        rollback_history_table = dynamodb.Table(
            self,
            "RollbackHistoryTable",
            partition_key=dynamodb.Attribute(
                name="rollback_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Lambda function to handle automated rollbacks when CloudWatch alarms trigger
        rollback_logger = lambda_.Function(
            self,
            "RollbackHandlerLambda",
            runtime=lambda_.Runtime.PYTHON_3_14,
            handler="rollback_handler.lambda_handler",
            code=lambda_.Code.from_asset("joshua/resources"),
            environment={
                "ROLLBACK_HISTORY_TABLE": rollback_history_table.table_name,
                "FUNCTION_NAME": fn.function_name,
                "ALIAS_NAME": alias.alias_name,
            },
        )

        # Grants the rollback lambda permissions to read/write history and manage function versions/aliases
        rollback_history_table.grant_read_write_data(rollback_logger)
        rollback_logger.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "lambda:ListVersionsByFunction",
                    "lambda:GetAlias",
                    "lambda:UpdateAlias",
                ],
                resources=[fn.function_arn, f"{fn.function_arn}:*"],
            )
        )
        # ==========================================

        # Invokes lambda function every x minutes
        rule = events.Rule(
            self,
            "LambdaInvocationRule",
            schedule=events.Schedule.rate(Duration.minutes(5)),
        )

        # Tells to invoke the lambda function when the rule is triggered
        rule.add_target(targets.LambdaFunction(alias))

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
                    period=Duration.minutes(2),
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
            # Maximum is used so that a 4xx or 5xx response is not hidden by successful responses.
            http_status_code_metrics.append(
                cloudwatch.Metric(
                    namespace="WebHealth",
                    metric_name="HTTP_STATUS_CODE",
                    statistic="Maximum",
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

        # Subscribe our custom rollback handler to the SNS topic so alarms trigger automated rollbacks
        topic.add_subscription(
            subscriptions.LambdaSubscription(rollback_logger)
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
                metric=http_status_code_metrics[i],
                threshold=400,
                evaluation_periods=2,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
                alarm_description=f"Alarm when {website_url} returns a 4xx or 5xx HTTP status code.",
            )

            # Destruction policy for the alarm.
            # If the stack is deleted, the alarm will be deleted as well.
            httpStatusAlarm.apply_removal_policy(RemovalPolicy.DESTROY)

            # When the alarm is triggered, the SNS topic will be notified.
            # This sends an email and invokes the alarm logger Lambda.
            httpStatusAlarm.add_alarm_action(alarm_action)


        # ==========================================
        # WEEK 11: Crawler Operational Alarms & Rollback Setup
        # ==========================================

        #Define operational metrics for your web crawler Lambda function
        crawler_errors_metric = alias.metric_errors(
            period=Duration.minutes(1),
            statistic="Sum"
        )
        
        crawler_duration_metric = alias.metric_duration(
            period=Duration.minutes(1),
            statistic="Average"
        )

        # Track how many times the crawler runs
        crawler_invocations_metric = alias.metric_invocations(
            period=Duration.minutes(5),
            statistic="Sum"
        )

        # Create alarms for these metrics
        crawler_error_alarm = cloudwatch.Alarm(
            self,
            "CrawlerErrorAlarm",
            metric=crawler_errors_metric,
            threshold=1,  # Triggers if there is 1 or more errors during deployment
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            alarm_description="Rollback trigger: Crawler threw an error.",
        )
        crawler_error_alarm.apply_removal_policy(RemovalPolicy.DESTROY)
        crawler_error_alarm.add_alarm_action(alarm_action)

        crawler_duration_alarm = cloudwatch.Alarm(
            self,
            "CrawlerDurationAlarm",
            metric=crawler_duration_metric,
            threshold=25,  # Triggers if processing time exceeds 25 seconds
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            alarm_description="Rollback trigger: Crawler processing time too high.",
        )
        crawler_duration_alarm.apply_removal_policy(RemovalPolicy.DESTROY)
        crawler_duration_alarm.add_alarm_action(alarm_action)

        crawler_invocations_alarm = cloudwatch.Alarm(
            self,
            "CrawlerInvocationsAlarm",
            metric=crawler_invocations_metric,
            threshold=1,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
            alarm_description="Rollback trigger: No crawler invocations in the last 10 minutes.",
        )
        crawler_invocations_alarm.apply_removal_policy(RemovalPolicy.DESTROY)
        crawler_invocations_alarm.add_alarm_action(alarm_action)
        # ==========================================
         # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_codedeploy/LambdaDeploymentGroup.html
        # Create CodeDeploy Deployment Group tied to these specific crawler alarms
        # deployment_group = codedeploy.LambdaDeploymentGroup(
        #     self,
        #     "DeploymentGroup",
        #     alias=alias,
        #     deployment_config=codedeploy.LambdaDeploymentConfig.CANARY_10_PERCENT_5_MINUTES, # <--- Updated
        #     alarms=[crawler_error_alarm, crawler_duration_alarm],
        # )


        # CloudWatch dashboard for website health monitoring
        dashboard = cloudwatch.Dashboard(
            self,
            "WebHealthDashboard",
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

            # New widget for Lambda Operational Health
            cloudwatch.GraphWidget(
                title="Crawler Operational Health (Invocations & Errors)",
                left=[crawler_invocations_metric],
                right=[crawler_errors_metric],
            ),
            cloudwatch.GraphWidget(
                title="Crawler Processing Duration",
                left=[crawler_duration_metric],
            ),
            cloudwatch.GraphWidget(
                title="Crawler Target DynamoDB Read Latency",
                left=[
                    cloudwatch.Metric(
                        namespace="CrawlerOperations",
                        metric_name="DynamoDBReadLatency",
                        dimensions_map={"Operation": operation},
                        period=Duration.minutes(1),
                        statistic="Average",
                    )
                    for operation in (
                        "get_target",
                        "list_targets",
                        "list_crawl_targets",
                    )
                ],
            ),
            cloudwatch.GraphWidget(
                title="Crawler Target DynamoDB Write Latency",
                left=[
                    cloudwatch.Metric(
                        namespace="CrawlerOperations",
                        metric_name="DynamoDBWriteLatency",
                        dimensions_map={"Operation": operation},
                        period=Duration.minutes(1),
                        statistic="Average",
                    )
                    for operation in (
                        "create_target",
                        "update_target",
                        "delete_target",
                    )
                ],
            ),
        )

        # I may have missed some info on topics/ alarm action / subscriptions. Though I'm not too sure.

        # Logging alarm information in DynamoDB database

        # Create dynamoDB, but pass it into the lambda function so it can write into the database?

############################## APPLIED PROJECT #####################################

# https://docs.aws.amazon.com/lambda/latest/dg/services-apigateway-tutorial.html 

#Build a public CRUD API Gateway endpoint for the web crawler to create/read/update/delete the target list containing the list of websites/webpages to crawl. First, place the target list in the database (DynamoDB). Then implement CRUD REST commands on DynamoDB entries. 


#Extend tests in each stage to cover the CRUD operations and DynamoDB read/write time.

#2 unit tests
#1 functional test
#1 integration test


# User interacts with the web crawler app using API gateway 


# Write API documentation and commit to github.


# Manage README files in markdown on GitHub.

# Lambda function for handling CRUD business logic
        crawler_crud_lambda = lambda_.Function(
            self,
            "CrawlerCrudLambda",
            runtime=lambda_.Runtime.PYTHON_3_14,
            handler="crawler_crud.lambda_handler",
            code=lambda_.Code.from_asset("joshua/resources"),
            environment={"CRAWLER_TARGETS_TABLE": crawler_targets_table.table_name},
        )

        # Grant Lambda read/write permissions to DynamoDB
        crawler_targets_table.grant_read_write_data(crawler_crud_lambda)
        crawler_crud_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
            )
        )

        # API Gateway REST API setup
        from aws_cdk import aws_apigateway as apigw

        api = apigw.RestApi(
            self,
            "CrawlerApi",
            rest_api_name="Web Crawler CRUD Service",
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=10,
                throttling_burst_limit=20,
            ),
        )

        # Root resource /targets
        targets_resource = api.root.add_resource("targets")
        targets_resource.add_cors_preflight(
            allow_origins=["*"],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type"],
        )
        targets_integration = apigw.LambdaIntegration(crawler_crud_lambda)

        # Add methods to /targets
        targets_resource.add_method("GET", targets_integration)   # List all
        targets_resource.add_method("POST", targets_integration)  # Create

        # Resource for specific item /targets/{target_id}
        single_target_resource = targets_resource.add_resource("{target_id}")
        single_target_resource.add_cors_preflight(
            allow_origins=["*"],
            allow_methods=["GET", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type"],
        )
        single_target_resource.add_method("GET", targets_integration)    # Read one
        single_target_resource.add_method("PUT", targets_integration)    # Update
        single_target_resource.add_method("DELETE", targets_integration) # Delete
        CfnOutput(
            self,
            "CrawlerApiUrl",
            value=api.url,
            description="Base URL for the public crawler targets REST API.",
        )