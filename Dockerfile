# =============================================================================
# Geo Services API — Dockerfile
# =============================================================================
# Multi-stage build for a lean production image.
# Base: python:3.11-slim (no GUI, no dev tools)
# Target: Azure Container Apps (consumption plan)
# =============================================================================

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies required by psycopg2 and geopandas
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Expose port
EXPOSE 8000

# Run with uvicorn
# Workers set to 1 for Azure Container Apps consumption plan
# Increase for dedicated plan deployments
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
