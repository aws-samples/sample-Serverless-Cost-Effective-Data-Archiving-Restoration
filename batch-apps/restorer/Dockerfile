
FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Copy the Python script
COPY restore.py .

# Install the required dependencies
RUN pip install boto3
# Run the Python script
CMD ["python3", "restore.py"]