FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml requirements.txt README.md ./

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY queuectl/ ./queuectl/
COPY tests/ ./tests/

# Install package in editable mode
RUN pip install --no-cache-dir -e .

# Environment variables for SQLite data path
ENV QUEUECTL_DB_PATH=/app/data/queue.db
ENV QUEUECTL_LOG_DIR=/app/data/logs
ENV QUEUECTL_PID_FILE=/app/data/workers.pid

# Create data volume directory
RUN mkdir -p /app/data

# Default entrypoint runs worker process continuously in foreground
CMD ["python", "-m", "queuectl.cli.main", "worker", "run"]
