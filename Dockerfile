FROM python:3.11-slim

# Create non-root user for security
RUN useradd --create-home appuser

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Drop privileges
USER appuser

# Start the HTTP healthcheck app which spawns the worker thread
CMD ["sh", "-c", "uvicorn worker.http_app:app --host 0.0.0.0 --port ${PORT:-8080}"]
