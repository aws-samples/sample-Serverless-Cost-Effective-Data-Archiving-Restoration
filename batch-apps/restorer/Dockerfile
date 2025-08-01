
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy the Python script
COPY restore.py .

# Install the required dependencies
RUN pip install boto3
# Run the Python script
CMD ["python3", "restore.py"]