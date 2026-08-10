import aws_cdk as core
import aws_cdk.assertions as assertions

from joshua_kramel.joshua_kramel_stack import JoshuaKramelStack


def test_lambda_and_schedule_created():
    app = core.App()
    stack = JoshuaKramelStack(app, "joshua-kramel")
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::Lambda::Function", 1)
    template.resource_count_is("AWS::Events::Rule", 1)
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "webhealth.lambda_handler",
        },
    )
