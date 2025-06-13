import os
import tarfile
import boto3
from botocore.exceptions import ClientError
import gzip
import shutil
import datetime

PROJECT_NAME=os.environ['PROJECT_NAME']
SOURCE_BUCKET = os.environ['SRC_BUCKET_NAME'] 
DEST_BUCKET = os.environ['DEST_BUCKET_NAME']
SOURCE_PREFIX = os.environ['PREFIX']+"/" 
now = datetime.datetime.now()
FILE_SIZE_LIMIT = int(os.environ['ARCHIVE_SIZE']) 
FILE_COUNT_LIMIT = int(os.environ['FILE_COUNT'])
DYNAMODB_TABLE_NAME = int(os.environ['table_name'])

print(f"Selected Project Name: {PROJECT_NAME}")
print(f"Source Bucket: {SOURCE_BUCKET}")
print(f"Destination Bucket: {DEST_BUCKET}")
print(f"Requested File Size Limit: {FILE_SIZE_LIMIT}")
print(f"Requested File Count Limit: {FILE_COUNT_LIMIT}")
print(f"MetaData Will be stored in: {DYNAMODB_TABLE_NAME}")

# Create S3 client
s3 = boto3.client('s3')

# List objects in the source prefix
print("Start Collecting files from S3")
# List all objects in the bucket in batches
all_objects = []
continuation_token = None
batch_count = 0

try:
    while True:
        # If we have a continuation token, include it in the request
        if continuation_token:
            response = s3.list_objects_v2(
                Bucket=SOURCE_BUCKET,
                Prefix=SOURCE_PREFIX,
                MaxKeys=1000,  # AWS limit is 1000 per request
                ContinuationToken=continuation_token
            )
        else:
            response = s3.list_objects_v2(
                Bucket=SOURCE_BUCKET,
                Prefix=SOURCE_PREFIX,
                MaxKeys=1000  # AWS limit is 1000 per request
            )
        
        # Get the objects from this batch
        batch_objects = response.get('Contents', [])
        batch_count += 1
        
        # Filter out directory-like objects (ending with / and 0 bytes)
        filtered_batch = [obj for obj in batch_objects if not (obj['Key'].endswith('/') and obj['Size'] == 0)]
        
        if filtered_batch:
            all_objects.extend(filtered_batch)
            print(f"Batch {batch_count}: Retrieved {len(filtered_batch)} files")
        
        # Check if there are more objects to retrieve
        if response.get('IsTruncated'):
            continuation_token = response.get('NextContinuationToken')
        else:
            break
    
    # Organize objects by subfolder
    objects_by_subfolder = {}
    for obj in all_objects:
        key = obj['Key']
        # Skip the prefix itself if it's returned
        if key == SOURCE_PREFIX:
            continue
            
        # Skip directory-like objects (ending with / and 0 bytes)
        if key.endswith('/') and obj['Size'] == 0:
            continue
            
        # Remove the main prefix to get relative path
        relative_path = key[len(SOURCE_PREFIX):]
        
        # Get the subfolder (first part of the path)
        parts = relative_path.split('/')
        if len(parts) > 1:
            subfolder = parts[0]
            if subfolder not in objects_by_subfolder:
                objects_by_subfolder[subfolder] = []
            objects_by_subfolder[subfolder].append(obj)
        else:
            # Files directly in the main prefix (no subfolder)
            if 'root' not in objects_by_subfolder:
                objects_by_subfolder['root'] = []
            objects_by_subfolder['root'].append(obj)
    
    # Print objects by subfolder
    print(f"\nObjects by subfolder in {SOURCE_PREFIX}:")
    for subfolder, subfolder_objects in objects_by_subfolder.items():
        print(f"\n{subfolder}/ ({len(subfolder_objects)} objects):")
        for obj in subfolder_objects[:10]:  # Limit display to 10 objects per subfolder
            print(f"  - {obj['Key']} ({obj['Size']} bytes)")
        if len(subfolder_objects) > 10:
            print(f"  ... and {len(subfolder_objects) - 10} more objects")
            
    objects = all_objects[:FILE_COUNT_LIMIT]  # Limit to the requested file count
    print(f"\nTotal files found: {len(all_objects)}")
    print(f"Files to process (limited by FILE_COUNT_LIMIT): {len(objects)}")
    
except ClientError as e:
    print(f"Error listing objects: {e}")
    exit(1)

print(f"Found {len(all_objects)} files in {SOURCE_BUCKET}/{SOURCE_PREFIX}")
# Create a temporary directory to download the files
temp_dir = 'app/s3-download'
os.makedirs(temp_dir, exist_ok=True)
# Import multiprocessing for parallel downloads
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# Function to download a single file
def download_s3_file(obj, bucket, temp_directory, s3_client):
    key = obj['Key']
    if key == SOURCE_PREFIX:
        return None
    
    local_path = os.path.join(temp_directory, os.path.basename(key))
    local_dir = os.path.dirname(local_path)
    os.makedirs(local_dir, exist_ok=True)
    
    try:
        s3_client.download_file(bucket, key, local_path)
        return local_path
    except ClientError as e:
        print(f"Error downloading {key}: {e}")
        return None

# Set up parallel download with ThreadPoolExecutor
print(f"Starting parallel download of {len(all_objects)} files...")
download_count = 0
batch_size = 100  # Process files in batches to show progress

# Create a session for thread safety
session = boto3.session.Session()
s3_thread_safe = session.client('s3')

# Use partial to create a function with preset arguments
download_func = partial(download_s3_file, 
                        bucket=SOURCE_BUCKET, 
                        temp_directory=temp_dir, 
                        s3_client=s3_thread_safe)

# Calculate optimal number of workers based on CPU cores
max_workers = min(32, multiprocessing.cpu_count() * 4)  # Limit to reasonable number
print(f"Using {max_workers} parallel workers for downloads")

# Process files in batches to show progress
for i in range(0, len(all_objects), batch_size):
    batch = all_objects[i:i+batch_size]
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(download_func, batch))
    
    # Count successful downloads
    successful = [r for r in results if r is not None]
    download_count += len(successful)
    
    # Show progress
    progress = (i + len(batch)) / len(all_objects) * 100
    print(f"Downloaded {download_count} files ({progress:.1f}% complete)")

print(f"Download completed: {download_count} files downloaded to {temp_dir}")


# Create DynamoDB client
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE_NAME)
files = os.listdir(temp_dir)


print(f"###########Zip in progress#####################")
# Create multiple tar files from the downloaded files
files_to_process = files.copy()
archive_count = 0
processed_files = []
created_archives = []

while files_to_process:
    # Generate a unique name for each archive
    archive_count += 1
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    archive_name = f"{PROJECT_NAME}_{timestamp}_part{archive_count}.tar.gz"
    tar_path = os.path.join(temp_dir, archive_name)
    created_archives.append(archive_name)
    
    print(f"Creating archive {archive_count}: {archive_name}")
    
    current_size = 0
    current_file_count = 0
    archive_files = []
    
    # Create a mapping of local filenames to their original S3 keys
    file_to_s3key = {}
    for obj in all_objects:
        key = obj['Key']
        basename = os.path.basename(key)
        file_to_s3key[basename] = key
    
    with tarfile.open(tar_path, 'w:gz') as tar:
        for file in files_to_process[:]:  # Use a slice copy to safely modify during iteration
            file_path = os.path.join(temp_dir, file)
            file_size = os.path.getsize(file_path)
            
            # Check if adding this file would exceed our limits
            if (current_size + file_size >= FILE_SIZE_LIMIT * 1024 * 1024) or (current_file_count >= FILE_COUNT_LIMIT):
                if current_file_count > 0:  # Only break if we've added at least one file
                    break
            
            # Add file to archive
            tar.add(file_path, arcname=file)  # Use arcname to store just the filename, not the full path
            current_size += file_size
            current_file_count += 1
            print(f"current_file_count  {current_file_count}:")
            print(f"current_size  {current_size}:")
                   
            archive_files.append(file)
            
            # Store the filename and tar file name in DynamoDB
            try:
                table.put_item(
                    Item={
                        'key': file,
                        'TarFileName': archive_name
                    }
                )
            except ClientError as e:
                print(f"Error storing {file} in DynamoDB: {e}")
    
    # Remove processed files from the list
    for file in archive_files:
        files_to_process.remove(file)
        processed_files.append(file)
        
        # Delete the original file from S3 after archiving
        if file in file_to_s3key:
            try:
                s3.delete_object(
                    Bucket=SOURCE_BUCKET,
                    Key=file_to_s3key[file]
                )
                print(f"Deleted {file_to_s3key[file]} from source bucket")
            except ClientError as e:
                print(f"Error deleting {file_to_s3key[file]} from source bucket: {e}")
    
    print(f"Archive {archive_count}: Added {current_file_count} files, size: {current_size/1024:.2f} KB")
    
    #Upload the tar file to the destination S3 bucket
    try:
        s3.put_object(
            Bucket=DEST_BUCKET, 
            Key=archive_name, 
            Body=open(tar_path, 'rb'), 
            StorageClass='DEEP_ARCHIVE'
        )
        print(f"Uploaded {archive_name} to {DEST_BUCKET}")
    except ClientError as e:
        print(f"Error uploading {archive_name} to {DEST_BUCKET}: {e}")
    
    # Optional: Remove the local archive after upload to save space
    os.remove(tar_path)
    print(f"Removed local archive: {tar_path}")
    
    # Break if we've processed all files
    if not files_to_process:
        break

print(f"File Manifest Stored in DynamoDB")
print(f"Created {archive_count} archives: {', '.join(created_archives)}")
print(f"Processed {len(processed_files)} files out of {len(files)} total files")
print(f"File Zip and Upload Completed")

# Clean up - remove the entire temporary directory
try:
    shutil.rmtree(temp_dir)
    print(f"Removed temporary directory: {temp_dir}")
except Exception as e:
    print(f"Error removing temporary directory: {e}")