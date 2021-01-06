This is a small sample of using DynamoDB to hold date exceptions for team/department or anything else that is referenced in the category field of the database.

The Lambda function will work on the current date/time and will query the database and if a record if found then it is considered an exception to the normal
hours of operation and will return an Action_Type and Action_String that the contact flow can use. The return status of 200 indicates a record/exception exists.



DynamoDB table

category: String
  This is used to group the records together
action_type: String
  This can be anything that you wish to invoke capability in the ContactFlow
  It could be:
    L - Label
    M - Message
    Q - Queue
    etc
    
action_string: String
  This is used to hold the actionable data based on the type:
  If you use the recommendations above then:
    L = a label that you could return ie "Team MTG", "Remembrance Day" then the Contact Flow contains the logic
    M = Text of message to be played, if the message starts with arn: then this will use a stored prompt
    Q = arn of the queue, as it may be out of hours you want contacts to goto a queue.
    
    
start_timestamp: String
  This is in the ISO format and can cover a period of time not just days so you can cater for team meetings if needed
  
end_timestamp: String
  When the close/exception ends



Lambda Function

The Lambda function uses two Environment Variables to specify the region and logging level

LOG_LEVEL
REGION

Policy Permissions

AmazonDynamoDBFullAccess

AWSLambdaDynamoDBExecutionRole

AWSLambdaBasicExecutionRole


