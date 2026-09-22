from aws_cdk import (
    Stage,
)
from constructs import Construct
from joshua_stack import JoshuaStack


class MyPipelineStage(Stage):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ApplicationStack = JoshuaStack(self, id="APP")