import boto3


# https://docs.aws.amazon.com/boto3/latest/reference/services/cloudwatch/client/list_metrics.html
def putDataFunc(namespace, metricName, url, value, unit):
    #creates a connection/interface to the CloudWatch API.
    client = boto3.client('cloudwatch')
    # Sends the metric data to CloudWatch
    response = client.put_metric_data(
        # Specifies which CloudWatch namespace the metric belongs to (webhealth).
        Namespace=namespace,
        # MetricData is a list containing the metric information
        # to be sent to cloudwatch
        MetricData=[
            {   # Specifies the name of the metric.
                'MetricName': metricName,
                # Adds a dimension to the metric.
                # A dimension provides additional information that identifies what the metric relates to
                'Dimensions': [
                    {
                        'Name': 'URL',
                        # Stores the URL of the website being monitored.                        
                        'Value': url
                    }
                ],
                # Specifies the unit of measurement for the value (e.g. latency or availability).
                'Unit': unit,
                # Specifies the actual measurement being sent to CloudWatch.
                'Value': float(value)
            }
        ]
    )
    # Returns the response received from CloudWatch.
    return response
