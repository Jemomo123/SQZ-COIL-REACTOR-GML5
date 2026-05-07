# ──────────────────────────────────────────────────────────────────────────
# RENDER FREE TIER BACKGROUND WORKER
# ──────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables for Python
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "main.py"]
