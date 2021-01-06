import json
import boto3
import logging
import os

from datetime import datetime


logger = logging.getLogger()
logger.setLevel(os.environ['LOG_LEVEL'])

# check if the inbound parameter causes a closed status to be return

dynamodb = boto3.resource('dynamodb', region_name=os.environ['REGION'])

def queryTable(category, timestampToCheck):
    # Now query Dynamodb based on reference and timestamp
    table = dynamodb.Table("scheduled_close")    

#
    try:
        response = table.query(
        KeyConditionExpression = "category = :category",
        FilterExpression = ":contact_timestamp between start_timestamp and end_timestamp",
        ExpressionAttributeValues = {
            ':category': category,
            ':contact_timestamp': timestampToCheck
        }

    )
    
    except IndexError as Ex:
        logger.debug('EX: No Items found')
        response = ""
   

    return format_return(response)
    
def format_return(response):
    # Now format return string
       
    if response != "":
        
        item = response["Items"][0]
        return {
            'scStatusCode': 200,
            'scActionType': item["action_type"],
            'scActionString': item["action_string"]
        }
    else:
        return {
            'scStatusCode': 404
        }


def lambda_handler(event, context):
    # TODO implement
    logger.debug('Event Stream: {}'.format(event))
      
    # USe contact timestamp to see of journey is open
    # OpenOrNot = queryTable("customer_service", "00261220T170000Z")    
    now = datetime.now().astimezone().isoformat()
    
    
    return queryTable("customer_service",now)
    
    