# Use a slim Python image
FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency files and metadata needed for installation
COPY pyproject.toml uv.lock README.md ./

# Install dependencies ONLY (skip project install for layer caching)
RUN uv sync --frozen --no-install-project

# Copy source code
COPY src/ ./src/

# Now install the project itself
RUN uv sync --frozen

# Environment variables defaults
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

# Run the scout module
CMD ["uv", "run", "-m", "scout.main"]
