import boto3
import constants
import CWPutData as cw
import time
import urllib.request

# Define metrics for a web URL. You will obtain and publish these metrics.
def lambda_handler(event, context):
    print(event)

    websites = [
        'https://www.westernsydney.edu.au/',
        'https://www.unsw.edu.au/',
        'https://www.sydney.edu.au/',
    ]

# https://docs.aws.amazon.com/boto3/latest/reference/services/cloudwatch/client/list_metrics.html
# https://docs.aws.amazon.com/boto3/latest/guide/cw-example-metrics.html
    client = boto3.client('cloudwatch')

    for site_url in websites:
        availability = 0
        latency = 0
        status_code = 0

        try:
            start_time = time.time()
            with urllib.request.urlopen(site_url, timeout=10) as response:
                status_code = response.getcode()
                availability = 1 if 200 <= status_code < 400 else 0
            latency = time.time() - start_time
        except Exception:
            availability = 0
            latency = 0
            status_code = 0

        response1 = client.put_metric_data(
            Namespace=constants.namespace,
            MetricData=[
                {
                    'MetricName': constants.metricAvailability,
                    'Dimensions': [
                        {
                            'Name': 'URL',
                            'Value': site_url
                        }
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
                        }
                    ],
                    'Unit': 'Seconds',
                    'Value': latency
                }
            ]
        )

        response3 = client.put_metric_data(
            Namespace=constants.namespace,
            MetricData=[
                {
                    'MetricName': constants.metricStatusCode,
                    'Dimensions': [
                        {
                            'Name': 'URL',
                            'Value': site_url
                        }
                    ],
                    'Unit': 'Count',
                    'Value': status_code
                }
            ]
        )

        cw.putDataFunc(constants.namespace, constants.metricAvailability, site_url, availability, 'None')
        cw.putDataFunc(constants.namespace, constants.metricLatency, site_url, latency, 'Seconds')
        cw.putDataFunc(constants.namespace, constants.metricStatusCode, site_url, status_code, 'Count')

    return {
        'statusCode': 200,
        'body': 'Metric publishing complete',
        'lastAvailabilityResponse': response1,
        'lastLatencyResponse': response2,
        'lastStatusCodeResponse': response3
    }

# If a component is part of your infrastructure, it should go into the stack file.