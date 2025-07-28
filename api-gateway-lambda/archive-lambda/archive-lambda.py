import os
import json
import boto3
import time

def lambda_handler(event, context):
    print("Received Event =>", event)
    print("Received Context =>", context)
    
    submit_batch_job(event)

def submit_batch_job(event):
    job_queue = os.environ['JOB_QUEUE']
    job_definition = os.environ['JOB_DEFINITION']
    #FILE_SIZE_LIMIT = int(os.environ['ARCHIVE_SIZE']) 
    env = [
        {'name': 'PROJECT_NAME', 'value': event['project_name']},
        {'name': 'SRC_BUCKET_NAME', 'value': event['bucket_name']},
        {'name': 'DEST_BUCKET_NAME', 'value': event['bucket_name'][:-3] + 'dest'},
        {'name': 'AWS_ACCOUNT', 'value': event['account']},
        {'name': 'AWS_REGION', 'value': event['region']},
        {'name': 'PREFIX', 'value': event['prefix']},
        {'name': 'FILE_COUNT', 'value': str(event['file_count'])},
        {'name': 'FILE_SIZE_LIMIT', 'value': str(event['archive_size'])},
        {'name': 'JOB_QUEUE', 'value': 'archiver-queue'},
        {'name': 'JOB_DEFINITION', 'value': 'archiver-jd'}
    ]
    if event['storage_class']:
        env.append({'name': 'STORAGE_CLASS', 'value': event['storage_class']})
    if event['archive_size']:
        env.append({'name': 'ARCHIVE_SIZE', 'value': str(event['archive_size'])})
    
    
    batch_client = boto3.client('batch')
    batch_client.submit_job(
        jobName=str(int(time.time())),
        jobQueue=job_queue,
        jobDefinition=job_definition,
        containerOverrides={
            'command': ['python3', 'archivemaster.py'],
            'environment': env
        }
    )
    
    return {
        'statusCode': 200,
        'body': json.dumps('Archival process completed successfully!')
    }