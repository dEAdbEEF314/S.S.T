# --- Stage 1: Build React Frontend ---
FROM node:20-slim AS build-frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Final Image ---
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-install-project

# Copy source code and build artifacts
COPY src/ ./src/
COPY --from=build-frontend /build/dist ./frontend/dist

# Install dependencies and project
RUN uv sync

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "src.ui.main:app", "--host", "0.0.0.0", "--port", "8000"]
