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
                # Website is considered available if it returns a 2xx or 3xx response.
                if 200 <= status_code < 400:
                    availability = 1
                else:
                    availability = 0

            latency = time.time() - start_time

        except Exception:
            # For now, if something goes wrong it will set the metrics to 0.
            availability = 0
            latency = 0
            status_code = 0

        # Sends the availability, latency, and status code metrics to CloudWatch
        # using the putDataFunc function from CWPutData.py.

        # Calls the putDataFunc function from CWPutData.py to send the metrics to CloudWatch. This is a more modular approach, as it allows for easier testing and maintenance of the code.
        cw.putDataFunc(
            constants.namespace,
            constants.metricAvailability,
            site_url,
            availability,
            'None'
        )

        cw.putDataFunc(
            constants.namespace,
            constants.metricLatency,
            site_url,
            latency,
            'Seconds'
        )

        cw.putDataFunc(
            constants.namespace,
            constants.metricStatusCode,
            site_url,
            status_code,
            'None'
        )

    # Returns a response to indicate that the metrics have been published successfully. The response includes the last responses from the put_metric_data calls for availability, latency, and status code metrics.
    return {
        'statusCode': 200,
        'body': 'Metric publishing complete'
    }

# If a component is part of your infrastructure, it should go into the stack file.
