# palmwtc — packaged Python project (uv-managed, requires-python >=3.11,<3.14)
FROM mcr.microsoft.com/devcontainers/python:3.13

RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv for fast, lockfile-faithful installs
RUN pip install --upgrade pip && pip install uv
