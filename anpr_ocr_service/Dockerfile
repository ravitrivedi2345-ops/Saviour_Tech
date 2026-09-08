# Multi-stage production Dockerfile for ANPR OCR Service
FROM python:3.11-slim

# System dependencies for OpenCV, GUI-less image processing, and networking
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . /app/

# Create non-root user for security
RUN useradd -m -u 1000 anpruser && \
    mkdir -p /app/logs/inferences && \
    chown -R anpruser:anpruser /app

USER anpruser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8001/api/v1/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
