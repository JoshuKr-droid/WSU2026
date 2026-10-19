from aws_cdk import (
    Aws,
    Stack,
    pipelines,
    SecretValue,
    aws_codepipeline_actions as codepipeline_actions,
    aws_iam as iam,
    Stage,
)
from constructs import Construct
from joshua.joshua_stack import JoshuaStack
from joshua.pipeline_stage import MyPipelineStage


# pipeline is region scoped

# https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.pipelines.html

class PipelineStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Access the CommitId of a GitHub source in the synth
        source = pipelines.CodePipelineSource.git_hub(
            repo_string="JoshuKr-droid/WSU2026",
            branch="main",
            authentication=SecretValue.secrets_manager("gitToken"),
            trigger=codepipeline_actions.GitHubTrigger.POLL,
        )

        synth = pipelines.ShellStep(
            id = "Synth",
            input=source,
            commands=[
                "npm install -g aws-cdk",
                "cd Joshua",
                "python -m pip install -r requirements.txt",
                "cdk synth",
            ],
            primary_output_directory="Joshua/cdk.out",
        )


        pipeline = pipelines.CodePipeline(self,
            id = "Pipeline",
            synth=synth,
        )

# https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk/Stage.html

# A stage is a class used to instantiate our application stack

# The alpha, beta, and gamma stages are below

# https://docs.aws.amazon.com/cdk/v2/guide/stages.html 
        Alpha = MyPipelineStage(self, "AlphaStage")

        pipeline.add_stage(
            stage = Alpha,
            post = [pipelines.ShellStep(
            id = "UnitTests",
            commands=[
                "npm install -g aws-cdk",
                "cd Joshua",
                "python -m pip install -r requirements.txt",
                "pip install pytest",
                "python -m pytest tests/unit",
            ]
        )])

        Beta = MyPipelineStage(self, "BetaStage")
        
        pipeline.add_stage(
            stage=Beta,
            post=[pipelines.ShellStep(
            id="FunctionalTests",
            commands=[
                "cd Joshua",
                "python -m pip install -r requirements.txt",
                "pip install pytest",
                "python -m pytest tests/functional",
            ],
        )])


        Gamma = MyPipelineStage(self, "GammaStage")
        
        pipeline.add_stage(
            stage=Gamma,
            post=[
                pipelines.CodeBuildStep(
                    id="IntegrationTests",
                    install_commands=[
                        "python -m pip install -r Joshua/requirements.txt",
                        "python -m pip install pytest",
                    ],
                    commands=[
                        "cd Joshua",
                        "python -m pytest tests/integration",
                    ],
                    env={
                        "RUN_AWS_INTEGRATION_TESTS": "true",
                        "AWS_DEFAULT_REGION": self.region,
                    },
                    env_from_cfn_outputs={
                        "CRAWLER_TARGETS_TABLE": (
                            Gamma.application_stack.crawler_targets_table_name_output
                        ),
                        "ALARM_LOG_TABLE": (
                            Gamma.application_stack.alarm_log_table_name_output
                        ),
                    },
                    role_policy_statements=[
                        iam.PolicyStatement(
                            actions=[
                                "dynamodb:GetItem",
                                "dynamodb:PutItem",
                                "dynamodb:UpdateItem",
                                "dynamodb:DeleteItem",
                                "dynamodb:Scan",
                            ],
                            resources=[
                                (
                                    f"arn:{Aws.PARTITION}:dynamodb:{self.region}:"
                                    f"{self.account}:table/*"
                                ),
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=["cloudwatch:PutMetricData"],
                            resources=["*"],
                        ),
                    ],
                ),
                pipelines.CodeBuildStep(
                    id="CanarySmokeTest",
                    env_from_cfn_outputs={
                        "CANARY_ALIAS_ARN": Gamma.application_stack.web_health_alias_arn_output,
                    },
                    commands=[
                        "aws lambda invoke --function-name \"$CANARY_ALIAS_ARN\" "
                        "--cli-binary-format raw-in-base64-out --payload '{}' "
                        "canary-response.json > canary-metadata.json",
                        "python3 -c 'import json, sys; metadata=json.load(open(\"canary-metadata.json\")); response=json.load(open(\"canary-response.json\")); sys.exit(\"Canary invocation failed: \" + json.dumps(metadata) if metadata.get(\"FunctionError\") or response.get(\"statusCode\") != 200 else 0)'",
                    ],
                    role_policy_statements=[
                        iam.PolicyStatement(
                            actions=["lambda:InvokeFunction"],
                            resources=[
                                Gamma.application_stack.web_health_alias.function_arn
                            ],
                        )
                    ],
                ),
            ],
        )

        prod = MyPipelineStage(self, "ProductionStage")
        pipeline.add_stage(
            stage = prod,
            pre=[pipelines.ManualApprovalStep("PromoteToProd",
                comment = "Please validate changes")]
        )

        
# https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.pipelines/ShellStep.html