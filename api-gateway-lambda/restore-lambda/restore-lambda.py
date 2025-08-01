import os
import boto3
import time
import json


def lambda_handler(event, context):
    print("Received Event =>", event)
    print("Received Context =>", context)
    PROJECT_NAME= event['project_name']
    AWS_ACCOUNT_PROVIDED= event['account']
    AWS_REGION_PROVIDED= event['region']
    REQUESTED_FILENAME_LIST = event['filename']
    RETRIEVAL_TIER = event['retrieval_tier']
    TOPIC_ARN = event['sns_topic_arn']
    ARCHIVAL_DYNAMODB_MASTER_TABLE= event['project_name'] + '_archive_master'

    SRC_BKT= event['dest_bucket_name']
    RESTORE_BKT = event['restore_bucket_name']
    
    print(f" Source bucket provided : {SRC_BKT}")
    print(f" Restore bucket provided : {RESTORE_BKT}")

    # Split by comma in case multiple file search
    REQUESTED_FILENAME_SEARCH = [f.strip() for f in REQUESTED_FILENAME_LIST.split(',')]

    for SEARCH_FILE_NAME in REQUESTED_FILENAME_SEARCH:
        print(f" Requested file name for search : {SEARCH_FILE_NAME}")
        resp = get_archive_details(SEARCH_FILE_NAME,ARCHIVAL_DYNAMODB_MASTER_TABLE)
        print(resp['Item'])

        TAR_FILE_NAME= resp['Item']['TarFileName']
        # Check if tarFileName is a dictionary
        if isinstance(TAR_FILE_NAME, dict):
        # Extract the filename from the dictionary
            TAR_FILE_NAME = list(TAR_FILE_NAME.values())[0]

        print(f" Requested file: {SEARCH_FILE_NAME} stored in tarFileName : {TAR_FILE_NAME}, Start the restore process")
        
        initiate_restore(AWS_ACCOUNT_PROVIDED,AWS_REGION_PROVIDED,SRC_BKT,TAR_FILE_NAME, SEARCH_FILE_NAME,RETRIEVAL_TIER,PROJECT_NAME,RESTORE_BKT,TOPIC_ARN)

    return {
        'statusCode': 200,
        'body': json.dumps('Restore Request process successfully!')
    }

def get_archive_details(requested_filename,table_name):
    dynamodb_client = boto3.client('dynamodb')
    response = dynamodb_client.get_item(
        TableName=table_name,
        Key={'key': {'S': requested_filename}}
    )
    return response

def initiate_restore(AWS_ACCOUNT_PROVIDED,AWS_REGION_PROVIDED,src_bkt,tarFileName, requested_filename,retrieval_tier,PROJECT_NAME,restore_bkt,TOPIC_ARN):
    print('Within initiate restore!!')
    print(f" src bucket : {src_bkt}")
    print(f" tarFileName : {tarFileName}")
    print(f" requested_filename : {requested_filename}")
    print(f" retrieval_tier : {retrieval_tier}")
    print(f" Restore bucket : {restore_bkt}")
    try:
        s3 = boto3.resource('s3')
        obj = s3.Object(src_bkt, tarFileName)
        head = obj.meta.client.head_object(Bucket=src_bkt, Key=tarFileName)
        print("Head Details =>", head)
        retrieval_tier = retrieval_tier if retrieval_tier in ['Expedited', 'Standard', 'Bulk'] else 'Standard'
        
        if head.get('StorageClass') == 'DEEP_ARCHIVE' and retrieval_tier == 'Expedited':
            retrieval_tier = 'Standard'
        
        print("Retrieval Tier =>", retrieval_tier)
    
        if 'Restore' not in head or head['Restore'] == 'false':
            print('Object to be restored!! Initiating restoration')
            try:
                s3_restore = boto3.client('s3', config=boto3.session.Config(connect_timeout=60, read_timeout=60))
                print(f"bucket name {src_bkt}")
                print(f"bucket Key {tarFileName}")
                response = s3_restore.restore_object(
                    Bucket=src_bkt,
                    Key=tarFileName,
                    RestoreRequest={'Days': 1, 'GlacierJobParameters': {'Tier': retrieval_tier}}
                )
                print("Response for restore:", response)
                record_restoration(src_bkt, tarFileName, requested_filename,PROJECT_NAME)
                # SNS Trigger
                sns = boto3.client('sns')
                message = f"S3 object {requested_filename} has been requested to restored from Glacier.Please Retry after 12hr"
                sns.publish(TopicArn=TOPIC_ARN, Message=message)
                print("SNS message published.")

            except Exception as e:
                print(f"Error restoring object: {e}")
        elif head['Restore'] == 'true':
            print('Object restoration is in progress; hence recording for future process')
            sns = boto3.client('sns')
            message = f"S3 object {requested_filename} has been requested to restored from Glacier.Please Retry after Sometime"
            sns.publish(TopicArn=TOPIC_ARN, Message=message)
            print("SNS message published.")
            record_restoration(src_bkt, tarFileName, requested_filename,PROJECT_NAME)
        else:
            print('Request for already restored archive')
            submit_batch_job(AWS_ACCOUNT_PROVIDED,AWS_REGION_PROVIDED,src_bkt, tarFileName, requested_filename, os.environ['TOPIC_ARN'],PROJECT_NAME,restore_bkt)
    except Exception as e:
        print(e)

def record_restoration(src_bkt, tarFileName, requested_filename,PROJECT_NAME):
    dynamodb_client = boto3.client('dynamodb')
    dynamodb_client.batch_write_item(
        RequestItems={
            PROJECT_NAME + '_restore_tracker': [
                {
                    'PutRequest': {
                        'Item': {
                            'key': {'S': requested_filename},
                            'archive_key': {'S': tarFileName},
                            's3_bucket': {'S': src_bkt}
                        }
                    }
                }
            ]
        }
    )

def submit_batch_job(AWS_ACCOUNT_PROVIDED,AWS_REGION_PROVIDED,s3_bucket, tarFileName,requested_filename, topic_arn,project_name,restore_bkt):
    print('Job Submitted for restoring the file!!')
    job_queue = os.environ['JOB_QUEUE']
    job_definition = os.environ['JOB_DEFINITION']

    batch_client = boto3.client('batch')
    batch_client.submit_job(
        jobName=str(int(time.time())),
        jobQueue=job_queue,
        jobDefinition=job_definition,
        containerOverrides={
            'command': ['python3', 'restore.py'],
            'environment': [
                {'name': 'PROJECT_NAME', 'value': project_name},
                {'name': 'SRC_BUCKET_NAME', 'value': s3_bucket},
                {'name': 'RESTORE_BUCKET_NAME', 'value': restore_bkt},
                {'name': 'AWS_ACCOUNT', 'value': AWS_ACCOUNT_PROVIDED},
                {'name': 'AWS_REGION', 'value': AWS_REGION_PROVIDED},
                {'name': 'ARCHIVE_KEY', 'value': tarFileName},
                {'name': 'KEY', 'value': requested_filename},
                {'name': 'TOPIC_ARN', 'value': topic_arn}
            ]
        }
    )