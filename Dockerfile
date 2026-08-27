# Multi‐stage build to reduce image size
ARG EXTRALIT_VERSION=latest
ARG EXTRALIT_SERVER_IMAGE=extralit/extralit-server

# Base stage with common dependencies from Extralit server
FROM ${EXTRALIT_SERVER_IMAGE}:${EXTRALIT_VERSION} AS base
USER root

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    apt-transport-https \
    gnupg \
    wget \
    lsb-release \
    ca-certificates

RUN wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch \
    | gpg --dearmor -o /usr/share/keyrings/elasticsearch-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/elasticsearch-keyring.gpg] https://artifacts.elastic.co/packages/8.x/apt stable main" \
    | tee /etc/apt/sources.list.d/elastic-8.x.list && \
    wget -qO - https://packages.redis.io/gpg \
    | gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/deb bookworm main" \
    | tee /etc/apt/sources.list.d/redis.list

# Create data directory

# Install Elasticsearch, Redis and utilities with apt cache mount
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    elasticsearch=8.17.0 \
    redis \
    curl \
    git \
    jq \
    pwgen && \
    chown -R extralit:extralit /usr/share/elasticsearch /etc/elasticsearch /var/lib/elasticsearch /var/log/elasticsearch && \
    chown extralit:extralit /etc/default/elasticsearch

RUN mkdir -p /data && chown extralit:extralit /data

COPY --chmod=0755 scripts/start.sh /home/extralit/start.sh
COPY --chmod=0755 Procfile /home/extralit/Procfile
COPY extralit_ocr /home/extralit/extralit_ocr
COPY config/elasticsearch.yml /etc/elasticsearch/elasticsearch.yml

# These layer on top of the base image's /opt/venv, which already holds extralit-server.
# `uv pip install`, never `uv sync`: sync makes the environment match a lockfile and would
# uninstall every server package it does not know about. `--python` names the venv explicitly
# rather than trusting VIRTUAL_ENV, so this keeps working against older base images.
# uv is bind-mounted, so the build never carries a copy of it into the shipped layers.
RUN --mount=from=ghcr.io/astral-sh/uv:0.12.6,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=/packages/pyproject.toml \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 \
    uv pip install --python /opt/venv/bin/python /packages && \
    apt-get remove -y wget gnupg && \
    apt-get autoremove -y

USER extralit

# Without this a crash can take its own traceback down with it: the Space's logs are the only
# way to see one, and honcho's pipes are not a tty, so Python block-buffers into them.
ENV PYTHONUNBUFFERED=1

# Environment variables for Elasticsearch
ENV ELASTIC_CONTAINER=true
ENV ES_JAVA_OPTS="-Xms1g -Xmx1g"

# Extralit home path for data
ENV EXTRALIT_HOME_PATH=/data/extralit
ENV REINDEX_DATASETS=1

# Expose the HTTP port for FastAPI & Elastic
EXPOSE 6900 9200 6379

# Start all services via Honcho/Procfile
CMD ["/bin/bash", "start.sh"]
