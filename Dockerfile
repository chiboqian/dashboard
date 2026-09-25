FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y iputils-ping curl && rm -rf /var/lib/apt/lists/*

# Copy local scripts
COPY requirements.txt ./
# We will create requirements.txt with pychromecast, etc.
RUN pip install --no-cache-dir pychromecast google-genai anthropic

COPY . .

# Run start script
CMD ["./start_dashboard.sh"]
