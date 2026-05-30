FROM mcr.microsoft.com/devcontainers/python:3.13

# Install uv
# RUN curl -LsSf https://astral.sh/uv/install.sh | sh
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV PATH="/root/.local/bin:$PATH"
