import os
import tarfile
import json
import boto3
import shutil
from botocore.exceptions import ClientError

PROJECT_NAME = os.environ['PROJECT_NAME']
archive_key = os.environ['ARCHIVE_KEY']
bucket_name = os.environ['SRC_BUCKET_NAME']
requested_file = os.environ['KEY']
sns_topic = os.environ['TOPIC_ARN']
restore_bucket=os.environ['RESTORE_BUCKET_NAME']
local_dir = 'app'
download_dir = local_dir+'/s3-download'
os.makedirs(download_dir, exist_ok=True)
restore_table=os.environ['PROJECT_NAME']+'_restore_tracker'
s3 = boto3.client('s3')
localfile=(f"{download_dir}/{archive_key}")
print(f"Start Collecting files from S3 into path {localfile}")
s3.download_file(bucket_name, archive_key,localfile )
os.chdir(download_dir)

try:
    with tarfile.open(archive_key, "r:gz") as tar_file:
        tar_file.extract(requested_file, path=f'{download_dir}/app/s3-download')
    # Check if abc.csv exists in the extracted files
    os.chdir(f'{download_dir}/app/s3-download')
    if os.path.exists(requested_file):
        # Get a list of all extracted files
        extracted_files = os.listdir(".")
        # Remove all files except abc.csv
        for file in extracted_files:
            if file != requested_file:
                os.remove(file)
    try:
        os.chdir(f'{download_dir}/app/s3-download')
        # Upload the files to the S3 bucket
        for file in os.listdir("."):
            s3.put_object(Bucket=restore_bucket, Key=file, Body=open(file, 'rb'))
        
        print(f"Uploaded {requested_file} to {restore_bucket}")
    except ClientError as e:
        print(f"Error uploading {requested_file} to {restore_bucket}: {e}")
    
    sns = boto3.client('sns')
    sns_resp = sns.publish(
        TopicArn=sns_topic,
        Message=f"File restored : {requested_file} from archive {archive_key} : Please Check S3 Bucket : {restore_bucket}",
        Subject=f'{requested_file} - File restored for Access'
    )
    print(sns_resp)

    try:
        dynamodb = boto3.client('dynamodb')
        del_resp = dynamodb.delete_item(
            Key={
                    'archive_key': {'S': archive_key},
                    'key': {'S': requested_file}
                },
                TableName=restore_table
            )
        print(f"Delete Response => {del_resp}")
    except ClientError as e:
                print(f"Error storing {file} in DynamoDB: {e}")

except ClientError as e:
    print(f"Error: {e}")

#Clean up the temporary directory
try:
    shutil.rmtree(download_dir, ignore_errors=True)
except OSError:
    pass