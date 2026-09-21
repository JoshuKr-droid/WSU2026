
from aws_cdk import (
    Stack,
    pipelines as pipelines,
    #Import some sort of github trigger??
)
from constructs import Construct

# https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.pipelines.html

class PipelineStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Access the CommitId of a GitHub source in the synth
        source = pipelines.CodePipelineSource.git_hub(
            repo_string = "owner/repo", #Put github repo
            branch = "main",
            authentication = SecretValue.secret_manager("gitToken"),
            trigger = "POLL"
        )
        
        synth = pipelines.ShellStep(
            id = "Synth",
            input = source,
            commands = ["nom install -g aws-cdk", "cd joshua/", "pip install -r requirements.txt", "cdk synth"]
            primary_output_directory = "joshua/cdk.out"
                # Use a connection created using the AWS console to authenticate to GitHub
                # Other sources are available.
                input=pipelines.CodePipelineSource.connection("my-org/my-app", "main",
                    connection_arn="arn:aws:codestar-connections:us-east-1:222222222222:connection/7d2469ff-514a-4e4f-9003-5ca4a43cdc41"
                ),
                commands=["npm ci", "npm run build", "npx cdk synth"]
        )
        
        pipeline = pipelines.CodePipeline(
            id = "pipeline",
            synth = synth,
        )
        
# All of this is based on me trying to follow the teacher
#Save name and token as a comment? #https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.pipelines/ShellStep.html