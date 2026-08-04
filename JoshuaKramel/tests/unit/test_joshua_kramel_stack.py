import aws_cdk as core
import aws_cdk.assertions as assertions

from joshua_kramel.joshua_kramel_stack import JoshuaKramelStack

# example tests. To run these tests, uncomment this file along with the example
# resource in joshua_kramel/joshua_kramel_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = JoshuaKramelStack(app, "joshua-kramel")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
