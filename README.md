## My Project

# Problem Statement.
Many organizations generate a large volume of files in Amazon S3 buckets from diverse sources. As part of a recurring workflow, these files undergo quality validation, and a summary report is produced for business stakeholders. Once the validation is reviewed and approved, the files are archived to S3 Glacier Deep Archive to optimize long-term storage costs. Currently, this archival is managed using a scheduled S3 Lifecycle policy. However, this method can lead to elevated costs due to bulk transition charges associated with time-based archival.

# Discovery Phase.
  1. It was observed that the files stored in Amazon S3 are rarely accessed, and stakeholders are willing to tolerate retrieval delays of up to 24 hours — aligning well with the characteristics of long-term archival storage.
  2. To ensure reliability, the archival process is automatically triggered via a scheduled cron job as a fallback mechanism, in case it is not initiated by the primary quality validation workflow.

# Business Requirement.
   1. Design a fully serverless solution to simplify operations and improve scalability.
   2. Optimize costs by minimizing Amazon S3 archival and transition charges.
   3. Expose an API endpoint that can be easily integrated with source systems for triggering the archival process.
   4. Implement a scheduled archival mechanism using a cron-based trigger to ensure timely fallback execution.
   5. Provide an API endpoint to initiate the restore process when users request access to archived files.


# AWS Service Used In Solution
- [ ] **Core Serverless Service**
	1. API Gateway
	2. AWS Lambda
	3. AWS S3
	4. AWS SNS
- [ ] **Non-Core Serverless service**
	1. ECR
	2. AWS Batch
	3. AWS ECS Fargate
	4. AWS CLoudWatch
	5. DynamoDB
	6. IAM

# Architecture
Below Solution architecture diagram to overcome the problem statement
 
 ![alt text](archtecture.png)
# Solution Overview
This solution creates a fully automated pipeline that handles archiving and restoring jobs using AWS Batch, Lambda functions, and API Gateway. The solution uses multiple AWS services for processing, job orchestration, and notifications
* The API Gateway provides an interface for initiating archiving or restoring jobs.
* AWS Batch handles the resource management and execution of jobs using the Docker images stored in ECR.
* DynamoDB tracks job states and stores metadata, providing efficient job management
* Lambda functions are invoked to perform specific steps (archiving, restoring, and completing the restore process).
* Notifications are sent to the provided email address upon completion of restoration.

## 📦 How the Solution Works


### 🔐 Archiving Process

1. **Trigger Archival**  
   The on-premises system triggers the `/archive` API with a manifest containing file count and total size.

2. **Archive Lambda Function**  
   - Validates the incoming request.  
   - Submits an AWS Batch job with file details for processing.

3. **AWS Batch (Fargate) Archival Job**  
   - Retrieves files from the source S3 bucket.  
   - Groups files based on size/count thresholds.  
   - Compresses them into `.zip` archives.

4. **Store in Glacier Deep Archive**  
   - Uploads the compressed `.zip` files to an S3 bucket configured with Glacier Deep Archive storage class.

5. **Track Metadata in DynamoDB**  
   - Stores metadata for each original file (e.g., archive location, zip structure) to enable efficient future retrieval.

---

### 🔁 Restoration Process

6. **Trigger Restoration**  
   - The `/restore` API is called with a list of files to be retrieved.

7. **Restore Lambda Function**  
   - Looks up file metadata and archive mappings from DynamoDB.  
   - Submits a restore job to AWS Batch with the required file details.

8. **AWS Batch (Fargate) Restore Job**  
   - Retrieves the necessary `.zip` archives from Glacier Deep Archive.  
   - Extracts only the requested files.  
   - Uploads them to a dedicated restore S3 bucket.

9. **Notification via SNS**  
   - Sends an email notification via Amazon SNS once the restore process is complete.

---

This end-to-end serverless solution ensures secure, cost-efficient, and scalable archiving and restoration of files using modern AWS cloud-native services.


## 🔐 Security Considerations

This solution adheres to AWS security best practices to ensure the confidentiality, integrity, and availability of data throughout the archiving and restoration lifecycle.

### ✅ IAM and Least Privilege Access

- All Lambda functions, AWS Batch jobs, and other resources use least-privilege IAM roles.
- IAM roles are scoped to only necessary permissions for services like S3, DynamoDB, SNS, and ECR.

### ✅ Network Security

- AWS Batch jobs use `awsvpc` mode and run in **private subnets** within a VPC.
- Lambda functions are deployed in the same VPC with restricted access.
- Security Groups are tightly controlled, typically allowing only HTTPS (443) outbound traffic.

### ✅ Data Protection

- Data at rest is stored in Amazon S3 with **Glacier Deep Archive**, encrypted using **SSE-S3** or **SSE-KMS**.
- All S3 interactions occur over **HTTPS**, ensuring data-in-transit encryption.
- Buckets enforce encryption via policies or default settings.

### ✅ API Security

- API Gateway endpoints support integration with IAM, API keys, or Amazon Cognito (based on implementation).
- Request validation and strict input checks help block malformed or malicious payloads.

### ✅ Monitoring and Logging

- All key services (Lambda, Batch, API Gateway) are integrated with **CloudWatch Logs**.
- **CloudTrail** is used for auditing and tracking API activity.

### ✅ Notifications and Alerts

- Notifications are sent via Amazon SNS with access managed through topic policies.
- Optional integration with CloudWatch alarms enables proactive alerting.

### ✅ Secure Container Execution

- Docker images are based on minimal, secure base images.
- Images are scanned for vulnerabilities using **Amazon ECR image scanning** before deployment.

### ✅ Secrets and Configuration

- No secrets or credentials are hardcoded.
- Sensitive configurations are passed securely using **AWS SAM parameters**.
- Use of **AWS Secrets Manager** or **SSM Parameter Store** is recommended for future secrets management.


This security model follows the AWS Well-Architected Framework’s Security Pillar and supports a secure, auditable, and resilient deployment.


## Prerequisites
* git to be installed. (https://git-scm.com/downloads)
* AWS CLI Installed & Configured. ( https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-install.html
https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html)
* Right IAM Privilege
* SAM Install (https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)
* To run this solution , you need VPC & Subnets details to deploy lamda function.

# Deployment Step

## Download the source from the repository
Clone the repository using the git command mentioned below or use any of your preferred methods of cloning the repository
```
git clone git@ssh.gitlab.aws.dev:USER/serverless-demo.git 
```

## Infrastructure Setup
```
sam deploy --guided -t infra_deploy.yaml

Configuring SAM deploy
======================

	Looking for config file [samconfig.toml] :  Found
	Reading default arguments  :  Success

	Setting default arguments for 'sam deploy'
	=========================================
	Stack Name [of]: <<Stack Name>>
	Project Name[]: <<Project Name>>
	AWS Region [us-east-2]: <<AWS Region>>
	Parameter VPCSelect [vpc-0817b363]: <<VPC selection>>
	Parameter SubnetSelect [subnet-c5e58889,subnet-75ac631e,subnet-172e2b6d]: <<Subnet Selection>>
	Parameter SGSelect [sg-bc307ac6]: <<Security Group Selection>>
	Parameter JobVCPUs [1]: <<Number of vCPU for each Job>>
	Parameter JobMemory [2048]: <<Memory allocation for each Job>>
	Parameter MaxCPUs [10]: <<Max number of vCPU allocated for this pipeline>>
	Parameter ENVFargatetype [FARGATE]: <<Execution mode>>
	Parameter RestoreNotification [user@amazon.com]: <<Notification SNS>>
	#Shows you resources changes to be deployed and require a 'Y' to initiate deploy
	Confirm changes before deploy [Y/n]: Y
	#SAM needs permission to be able to create roles to connect to the resources in your template
	Allow SAM CLI IAM role creation [Y/n]: Y
	Save arguments to configuration file [Y/n]: Y
	SAM configuration file [samconfig.toml]:
	SAM configuration environment [default]:
```
## Create Docker Image & upload to ECR
1. Deploy all the images to ECR 
Traverse to ```batch-apps/scripts``` directory from the project directory and execute the below command.
```
./deploy-object-images.sh <projectname> <AccountNumber> <Region to store Image>
example:
./deploy-object-images.sh myproject 123456789012 us-west-2
```
2. User Input for the scripts while execution
While executing the script suggested above, below prompts for the user inputs. 
```
Project name: <<Project Name>>
AWS Account ID: <<Enter Account ID>
AWS Region: <<Enter AWS Region>
```

## Identifying API Gateway endpoint.
Once Cloudformation is successfully deployed, follow the below steps 
1. Open the "CloudFormation" Console.
2. Select "Stacks" on the navigational pane.
3. select the stack name you provided during the deploy.
4. Select "Outputs" section in the pane.
5. Find the API Gateway endpoint against the "RootUrl" attribute.

## Testing the Solution 
### Archive command
```
curl --location --request POST '<<API Gateway Endpoint>>/live/archive' \
--header 'Content-Type: application/json' \
--data-raw '{
"project_name": "<Project Name>",
"bucket_name": "<<sorce Bucket Name>>",
"prefix": "<<S3 Prefix you like to Fuse>>",
"file_count": <<Number of file count you like to archive>>,
"archive_size": <<Size Cap in MB>>,
"region": "<<AWS Region>>",
"storage_class": "<<Storage Class>>"
}'

Command with sample data

curl --location --request POST 'https://tlk5v3eh6j.execute-api.us-east-1.amazonaws.com/LATEST/archive' \
--header 'Content-Type: application/json' \
--data-raw '{
"project_name": "amazon"
"bucket_name": "amazon-1234567890-us-east-1_src",
"prefix": "20250410",
"file_count": 50000,
"archive_size": 500, 
"account": "1234567890",
"region": "us-east-1",
"storage_class": "GLACIER",
"output_prefix": "amazon-20240410"
}'


```

### Restore File Command
```
curl --location --request POST '<<API Gateway Endpoint>>/latest/restore' \
--header 'Content-Type: application/json' \
--data-raw '{
"project_name": "<Project Name>",
"filename": "<<file name to Restore>>",
"region": "<<AWS Region>>",
"retrieval_tier": "<<Retrieval Tier>>",
"sns_topic_arn": "<<sns topic arn>>"
}'

Command with sample data

curl --location --request POST 'https://izzucr336g.execute-api.ap-south-1.amazonaws.com/LATEST/restore' \
--header 'Content-Type: application/json' \
--data-raw '{
"project_name": "amazon",
"filename": "5000_20240517_003.csv",
"account": "1234567890",
"region": "ap-south-1",
"retrieval_tier": "Expedited",
"sns_topic_arn": "ARN"
}'

```
# cleanUp
The SAM CLI's delete command will prompt for confirmation before deleting resources, which is helpful to prevent accidental deletions.
```
./batch-apps/scripts/cleanup-object-images.sh
sam delete --stack-name YOUR_STACK_NAME 
```


# Outcome
The solution achieves the following outcomes:

 **Cost Optimization**: Significantly reduces S3 archival costs by leveraging a serverless, event-driven architecture with minimal manual intervention.

 **Scalability**: A serverless approach using AWS Batch and Lambda functions scales seamlessly with the volume of files.

 **Efficiency**: Automates archiving and restoration processes with a well-defined API interface for integration with other systems.
 
 **Ease of Use**: API endpoints allow for easy integration with the Quality Check system and straightforward file restoration requests.
## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.

