# ──────────────────────────────────────────────────────────────────────────
# IMPORTANT: Explicitly use Python 3.11 to avoid Pandas compile errors on 3.14
# ──────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install minimal build tools
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
