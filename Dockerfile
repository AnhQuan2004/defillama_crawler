FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# No need to install browsers as they're already included in the base image
# But we can verify they're installed
RUN playwright install-deps chromium

# Copy source code
COPY . .

# Expose port
EXPOSE 8080

# Change CMD line in Dockerfile to:
CMD ["python", "app.py"]