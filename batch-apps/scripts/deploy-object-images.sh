#!/bin/bash

# Check if project name is provided
if [ -z "$1" ]; then
  projectName="demo"
  echo "No project name provided, using default: $projectName"
else
  projectName=$1
  echo "Using project name: $projectName"
fi
# Check if Account Number is provided
if [ -z "$2" ]; then
  acctId=1234567890
  echo "No Account Number provided, using default: $acctId"
else
  acctId=$2
  echo "Using Account Number: $acctId"
fi
# Check if Region is provided
if [ -z "$3" ]; then
  awsRegion='us-east-1'
  echo "No Region provided, using default: $awsRegion"
else
  awsRegion=$3
  echo "Using Region: $awsRegion"
fi

# Create and use a new builder instance
docker buildx create --use

echo "Login to Repository"
aws ecr get-login-password --region $awsRegion | docker login --username AWS --password-stdin $acctId.dkr.ecr.$awsRegion.amazonaws.com

echo "Starting deployment of Archive Master"
cd ../archive-master
pwd  # Check if we're in the right directory

# Build using buildx with proper platform specification
docker buildx build --platform=linux/amd64 \
  --load \
  -t ${projectName}-archivemaster .

# Tag and push if build successful
if [ $? -eq 0 ]; then
    docker tag ${projectName}-archivemaster:latest $acctId.dkr.ecr.$awsRegion.amazonaws.com/${projectName}-archivemaster:latest
    docker push $acctId.dkr.ecr.$awsRegion.amazonaws.com/${projectName}-archivemaster:latest
    echo "Archive Master build and push successful"
else
    echo "Archive Master build failed"
    exit 1
fi

echo "Starting deployment of Restorer"
cd ../restorer

# Build restorer using buildx
docker buildx build --platform=linux/amd64 \
  --load \
  -t ${projectName}-restorer .

# Tag and push if build successful
if [ $? -eq 0 ]; then
    docker tag ${projectName}-restorer:latest $acctId.dkr.ecr.$awsRegion.amazonaws.com/${projectName}-restorer:latest
    docker push $acctId.dkr.ecr.$awsRegion.amazonaws.com/${projectName}-restorer:latest
    echo "Restorer build and push successful"
else
    echo "Restorer build failed"
    exit 1
fi

# Clean up dangling images
echo "Cleaning Dangling images"
docker image prune -f
echo "Cleanup Complete!"

echo "Image Uploaded Sucessfully"
