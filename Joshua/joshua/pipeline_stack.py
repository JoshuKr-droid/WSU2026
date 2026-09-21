from aws_cdk import (
    Stack,
    pipelines,
    SecretValue,
    aws_codepipeline_actions as codepipeline_actions,
)
from constructs import Construct

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
            "Synth",
            input=source,
            commands=[
                "npm install -g aws-cdk",
                "python -m pip install --upgrade pip",
                "python -m pip install -r joshua/requirements.txt",
                "cdk synth",
            ],
            primary_output_directory="cdk.out",
        )

        pipeline = pipelines.CodePipeline(
            self,
            "Pipeline",
            synth=synth,
        )

# All of this is based on me trying to follow the teacher
# Save name and token as a comment?
# https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.pipelines/ShellStep.html