FROM python:3.11-slim

WORKDIR /app

# Install system deps for common crypto/cert needs
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000

# Use Gunicorn with Uvicorn worker for production
CMD ["gunicorn","-k","uvicorn.workers.UvicornWorker","app:app","--bind","0.0.0.0:8000","--workers","1"]
