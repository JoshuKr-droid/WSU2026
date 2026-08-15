import boto3


# https://docs.aws.amazon.com/boto3/latest/reference/services/cloudwatch/client/list_metrics.html
def putDataFunc(namespace, metricName, url, value, unit):
    client = boto3.client('cloudwatch')

    response = client.put_metric_data(
        Namespace=namespace,
        MetricData=[
            {
                'MetricName': metricName,
                'Dimensions': [
                    {
                        'Name': 'URL',
                        'Value': url
                    }
                ],
                'Unit': unit,
                'Value': float(value)
            }
        ]
    )

    return response
