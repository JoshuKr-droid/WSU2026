from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda as lambda_,
)
from constructs import Construct


class JoshuaKramelStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

         # The code that defines your stack goes here

        # example resource
        # queue = sqs.Queue(
        #     self, "JoshuaKramelQueue",
        #     visibility_timeout=Duration.seconds(300),
        # )

        fn = lambda_.Function(
            self,
            "WebHealthLambda",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="webhealth.lambda_handler",
            code=lambda_.Code.from_asset("joshua_kramel/resources"),
            timeout=Duration.seconds(30),
        )
        fn.apply_removal_policy(RemovalPolicy.DESTROY)

        rule = events.Rule(
            self,
            "LambdaInvocationRule",
            schedule=events.Schedule.rate(Duration.minutes(30)),
        )
        rule.add_target(targets.LambdaFunction(fn))
        rule.apply_removal_policy(RemovalPolicy.DESTROY)
