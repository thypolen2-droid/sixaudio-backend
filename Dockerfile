# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PORT 8080

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements_cloud.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements_cloud.txt

# Copy the current directory contents into the container at /app
COPY . .

# Expose port 8080 (Cloud Run default)
EXPOSE 8080

# Run the app. Note: we point to our specific cloud runner
CMD ["uvicorn", "modules.server:app", "--host", "0.0.0.0", "--port", "8080"]
