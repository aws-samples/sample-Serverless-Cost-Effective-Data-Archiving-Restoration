import os
import boto3
import time
import json


def lambda_handler(event, context):
    print("Received Event =>", event)
    print("Received Context =>", context)
    PROJECT_NAME= event['project_name']
    AWS_ACCOUNT= event['account']
    AWS_REGION= event['region']
    requested_filename = event['filename']
    retrieval_tier = event['retrieval_tier']
    TOPIC_ARN = event['sns_topic_arn']
    archival_table={PROJECT_NAME}+'_archive_master'

    resp = get_archive_details(requested_filename,archival_table)
    print(resp['Item'])

    tarFileName = resp['Item']['TarFileName']
    # Check if tarFileName is a dictionary
    if isinstance(tarFileName, dict):
    # Extract the filename from the dictionary
        tarFileName = list(tarFileName.values())[0]

    print(f" tarFileName extracted from dynamodb : {tarFileName}")
    src_bkt ='{PROJECT_NAME}-'+{AWS_ACCOUNT}+'-'+{AWS_REGION}+'-dest'
    restore_bkt ='{PROJECT_NAME}-'+{AWS_ACCOUNT}+'-'+{AWS_REGION}+'-restore'

    initiate_restore(src_bkt,tarFileName, requested_filename,retrieval_tier,PROJECT_NAME,restore_bkt,TOPIC_ARN)

    return {
        'statusCode': 200,
        'body': json.dumps('Restore Request process  successfully!')
    }

def get_archive_details(requested_filename,table_name):
    dynamodb_client = boto3.client('dynamodb')
    response = dynamodb_client.get_item(
        TableName=table_name,
        Key={'key': {'S': requested_filename}}
    )
    return response

def initiate_restore(src_bkt,tarFileName, requested_filename,retrieval_tier,PROJECT_NAME,restore_bkt,TOPIC_ARN):
    print('Within initiate restore!!')
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
            submit_batch_job(src_bkt, os.environ['AWS_'],os.environ['AWS_REGION'], tarFileName, requested_filename, os.environ['TOPIC_ARN'],PROJECT_NAME,restore_bkt)
    except Exception as e:
        print(e)

def record_restoration(src_bkt, tarFileName, requested_filename,PROJECT_NAME):
    dynamodb_client = boto3.client('dynamodb')
    dynamodb_client.batch_write_item(
        RequestItems={
            {PROJECT_NAME}+'_restore_tracker': [
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

def submit_batch_job(s3_bucket, aws_account,aws_region, tarFileName,requested_filename, topic_arn,PROJECT_NAME,restore_bkt):
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
                {'name': 'PROJECT_NAME', 'value': PROJECT_NAME},
                {'name': 'SRC_BUCKET_NAME', 'value': s3_bucket},
                {'name': 'RESTORE_BUCKET_NAME', 'value': restore_bkt},
                {'name': 'AWS_ACCOUNT', 'value': aws_account},
                {'name': 'AWS_REGION', 'value': aws_region},
                {'name': 'ARCHIVE_KEY', 'value': tarFileName},
                {'name': 'KEY', 'value': requested_filename},
                {'name': 'TOPIC_ARN', 'value': topic_arn}
            ]
        }
    )