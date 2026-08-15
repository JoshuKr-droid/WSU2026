import boto3
import constants
import CWPutData as cw

# Define metrics for a web URL. You will obtain and publish these metrics.
def lambda_handler(event, context):
    print(event)

    # You compute the metrics in this application.
    # Following values are used as an example. You are expected to compute these.
    availability = 0
    latency = 0.23
    site_url = 'https://www.westernsydney.edu.au/'

# https://docs.aws.amazon.com/boto3/latest/reference/services/cloudwatch/client/list_metrics.html
    client = boto3.client('cloudwatch')

    response1 = client.put_metric_data(
        Namespace=constants.namespace,
        MetricData=[
            {
                'MetricName': constants.metricAvailability,
                'Dimensions': [
                    {
                        'Name': 'URL',
                        'Value': site_url
                    },
                ],
                'Unit': 'None',
                'Value': availability
            }
        ]
    )

    response2 = client.put_metric_data(
        Namespace=constants.namespace,
        MetricData=[
            {
                'MetricName': constants.metricLatency,
                'Dimensions': [
                    {
                        'Name': 'URL',
                        'Value': site_url
                    },
                ],
                'Unit': 'Seconds',
                'Value': latency
            }
        ]
    )

    # The helper file can also be used for the same metric pattern.
    cw.putDataFunc(constants.namespace, constants.metricAvailability, site_url, availability, 'None')
    cw.putDataFunc(constants.namespace, constants.metricLatency, site_url, latency, 'Seconds')

    return {
        'statusCode': 200,
        'body': 'Metric publishing complete',
        'availabilityResponse': response1,
        'latencyResponse': response2
    }

# If a component is part of your infrastructure, it should go into the stack file.