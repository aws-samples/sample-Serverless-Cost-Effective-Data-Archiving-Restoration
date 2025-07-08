FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Install the required dependencies with specific versions for security
RUN pip install --no-cache-dir boto3==1.34.11

# Create a non-root user and switch to it
RUN adduser --disabled-password --gecos "" --uid 1000 appuser

# Copy the Python script with proper permissions
COPY --chown=appuser:appuser restore.py .

# Set secure environment variables for TLS enforcement
ENV AWS_USE_HTTPS=1
ENV AWS_S3_ENFORCE_SSL=1

# Switch to non-root user
USER appuser

# Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python3 -c "import sys; sys.exit(0)" || exit 1

# Run the Python script
CMD ["python3", "restore.py"]