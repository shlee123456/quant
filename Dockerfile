# Multi-stage build for trading bot container
# Stage 1: Builder - Install dependencies
FROM python:3.11-slim AS builder

LABEL maintainer="Trading Bot Team"
LABEL description="Multi-asset trading bot with backtesting and strategy optimization"

# Set working directory
WORKDIR /app

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements files
COPY requirements.txt .
COPY requirements-ml.txt .

# Install Python dependencies
# --no-cache-dir: Don't cache pip packages (reduces image size)
# --user: Install to user site-packages
# CPU-only torch to reduce image size (~800MB vs ~2GB with CUDA)
RUN pip install --no-cache-dir --user -r requirements.txt && \
    pip install --no-cache-dir --user \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements-ml.txt

# ============================================
# Stage 2: Runtime - Create final image
# ============================================
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder to system location
# This allows any user to access the packages
COPY --from=builder /root/.local /usr/local

# Copy application code
COPY trading_bot/ ./trading_bot/
COPY dashboard/ ./dashboard/
COPY examples/ ./examples/
COPY scripts/ ./scripts/
COPY scheduler.py ./scheduler.py

# Create directories for data, logs, and reports
RUN mkdir -p /app/data /app/logs /app/config /app/reports

# Create non-root user for security (UID 1001 matches host user)
RUN useradd -m -u 1001 trader && \
    chown -R trader:trader /app

# Switch to non-root user
USER trader

# Expose Streamlit dashboard port
EXPOSE 8501

# Health check for Streamlit dashboard
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=40s \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Default command: Run Streamlit dashboard
CMD ["streamlit", "run", "dashboard/app.py", "--server.address", "0.0.0.0"]
