from aws_cdk import (
    Stack,
    pipelines,
    SecretValue,
    aws_codepipeline_actions as codepipeline_actions,
    Stage,
)
from constructs import Construct
from joshua_stack import JoshuaStack
from pipeline_stage import MyPipelineStage

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
                "python -m pytests",
            ],
            primary_output_directory="Joshua/cdk.out",
        )])

        Beta = MyPipelineStage(self, "Beta Stage")
        
        pipeline.add_stage(
            stage = Alpha,
            post = [run functional tests here])

        Gamma = MyPipelineStage(self, "Gamma Stage")
        
        pipeline.add_stage(
            stage = Alpha,
            post = [run integration tests here])

        prod = MyPipelineStage(self, "Production Stage")
        pipeline.add_stage(
            stage = prod,
            pre=[pipelines.ManualApprovalStep("PromoteToProd",
                comment = "Please validate changes")]
        )

        


# https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.pipelines/ShellStep.html