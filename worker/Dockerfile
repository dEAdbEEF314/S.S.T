FROM python:3.12-slim

# Install uv and ffmpeg
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN apt-get update && apt-get install -y ffmpeg libmagic1 && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files and metadata
COPY pyproject.toml uv.lock README.md ./

# Install dependencies ONLY
RUN uv sync --no-install-project
COPY src/ ./src/
RUN uv sync

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

# Run the Prefect worker process
CMD ["uv", "run", "prefect", "worker", "start", "--pool", "sst-worker-pool"]
