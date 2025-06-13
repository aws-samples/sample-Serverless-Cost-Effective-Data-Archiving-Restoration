FROM --platform=linux/amd64 python:3.9-slim

WORKDIR /app

COPY archivemaster.py .

RUN pip install boto3

CMD ["python3", "archivemaster.py"]