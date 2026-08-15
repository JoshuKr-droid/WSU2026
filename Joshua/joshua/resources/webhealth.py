#This file is the project application

#Define 3 metrics for a web url. You will obtain and print those metrics

def lambda_handler(event, context):
    print(event)
    return 'Hello from Lambda!'