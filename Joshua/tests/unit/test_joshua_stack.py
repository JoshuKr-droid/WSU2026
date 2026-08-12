import aws_cdk as core
import aws_cdk.assertions as assertions

from joshua.joshua_stack import JoshuaStack

# example tests. To run these tests, uncomment this file along with the example
# resource in joshua/joshua_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = JoshuaStack(app, "joshua")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
