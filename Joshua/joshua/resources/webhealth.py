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

    # Runs each site in the list and runs the following code to obtain the metrics and publish them to CloudWatch.
    for site_url in websites:
        availability = 0
        latency = 0
        status_code = 0

        try:
            start_time = time.time()
            # Opens the URL and waits for a response. If the response is received within 10 seconds,
            # it will continue to the next line of code. If not, it will raise an exception.
            with urllib.request.urlopen(site_url, timeout=10) as response:
                status_code = response.getcode()
                availability = 1 if 200 <= status_code < 400 else 0
            latency = time.time() - start_time
        except Exception:
            # For now, if something goes wrong it will set the metrics to 0.
            availability = 0
            latency = 0
            status_code = 0

        # Sends the availability, latency, and status code metrics to CloudWatch
        # using the putDataFunc function from CWPutData.py.
        response1 = client.put_metric_data(
            Namespace=constants.namespace,
            MetricData=[
                {
                    'MetricName': constants.metricAvailability,
                    # Tells which website the metric is for
                    'Dimensions': [
                        {
                            'Name': 'URL',
                            'Value': site_url
                        }
                    ],
                    # No specefic unit for availability metric, as it is a binary value (0 or 1)
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
                    # Unit for latency metric is seconds, as it measures the time taken to receive a response from the website
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
                    # Unit for status code metric is count, as it counts the number of occurrences of each status code
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