import json
import logging
import base64

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)




def lambda_handler(event, context):
    """
    This function is called by Kinesis Firehose when the option to transform
    the records is checked and this lambda function is invoked

    Args:
        event (dict): Containts the payload of records been passed by Kinesis
        context (dict): Not used

    Returns:
        [dict]: returns the list of transformed records
    """


    output = []
    
    logger.debug("Received event: " + json.dumps(event, indent=2))
    for record in event['records']:
        # Kinesis data is base64 encoded so decode here
        payload = base64.b64decode(record['data'])
        logger.debug("Decoded payload: {}".format(payload))
    
        # If result is:
        # Ok - record is processed
        # Dropped - record is not processed by kinesis
    
        output_record = {
            "recordId" : record["recordId"],
            "result" : "Ok",
            "data" : base64.b64encode(payload)
            
        }
        output.append(output_record)
    
    #return 'Successfully processed {} records.'.format(len(event['records']))
    logger.debug("Output: {}".format(output))
    return {
        "records" : output
    }
