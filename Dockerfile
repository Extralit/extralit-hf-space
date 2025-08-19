# Multi‐stage build to reduce image size
ARG EXTRALIT_VERSION=latest
ARG EXTRALIT_SERVER_IMAGE=extralit/extralit-server

# Base stage with common dependencies from Extralit server
FROM ${EXTRALIT_SERVER_IMAGE}:${EXTRALIT_VERSION} AS base
USER root

# Copy HF-Space startup scripts and Procfile
COPY scripts/start.sh /home/extralit/start.sh
COPY Procfile /home/extralit/Procfile
COPY pyproject.toml /packages/pyproject.toml
COPY src /home/extralit/src

# Install required APT dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    apt-transport-https \
    gnupg \
    wget \
    lsb-release \
    ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Add Elasticsearch repository
RUN wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch \
    | gpg --dearmor -o /usr/share/keyrings/elasticsearch-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/elasticsearch-keyring.gpg] https://artifacts.elastic.co/packages/8.x/apt stable main" \
    | tee /etc/apt/sources.list.d/elastic-8.x.list

# Add Redis repository
RUN wget -qO - https://packages.redis.io/gpg \
    | gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/deb $(lsb_release -cs) main" \
    | tee /etc/apt/sources.list.d/redis.list

RUN apt-get update

# Create data directory
RUN mkdir -p /data && chown extralit:extralit /data

# Install Elasticsearch (pinned) and fix permissions
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends elasticsearch=8.17.0 && \
    chown -R extralit:extralit /usr/share/elasticsearch /etc/elasticsearch /var/lib/elasticsearch /var/log/elasticsearch && \
    chown extralit:extralit /etc/default/elasticsearch

# Install Redis server
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends redis

# Install Python deps, utilities, then clean up
RUN uv pip install --no-cache-dir /packages && \
    chmod +x /home/extralit/start.sh /home/extralit/Procfile && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl jq pwgen && \
    apt-get remove -y wget gnupg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /packages

# Copy Elasticsearch config
COPY config/elasticsearch.yml /etc/elasticsearch/elasticsearch.yml

USER extralit

# Environment variables for Elasticsearch
ENV ELASTIC_CONTAINER=true
ENV ES_JAVA_OPTS="-Xms1g -Xmx1g"

# Extralit home path for data
ENV EXTRALIT_HOME_PATH=/data/extralit
ENV REINDEX_DATASETS=1

# Expose the HTTP port for FastAPI & Elastic
EXPOSE 80 9200 6379

# Start all services via Honcho/Procfile
CMD ["/bin/bash", "start.sh"]
