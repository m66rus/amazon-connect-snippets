This is a small sample of using DynamoDB to hold date exceptions for team/department or anything else that is referenced in the category field of the database.

The Lambda function will work on the current date/time and will query the database and if a record if found then it is considered an exception to the normal
hours of operation and will return an Action_Type and Action_String that the contact flow can use. The return status of 200 indicates a record/exception exists.

