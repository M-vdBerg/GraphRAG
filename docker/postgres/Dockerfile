FROM postgres:16

# Build AGE from source (no official apt package for pg16 in all distros)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        build-essential \
        git \
        postgresql-server-dev-16 \
        libreadline-dev \
        zlib1g-dev \
        bison \
        flex \
    && rm -rf /var/lib/apt/lists/*

# Install pgvector
RUN git clone --depth 1 --branch v0.7.4 https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && cd /tmp/pgvector \
    && make \
    && make install \
    && rm -rf /tmp/pgvector

# Install Apache AGE
RUN git clone --depth 1 --branch PG16/v1.5.0-rc0 https://github.com/apache/age.git /tmp/age \
    && cd /tmp/age \
    && make \
    && make install \
    && rm -rf /tmp/age

# Remove build deps to slim the image
RUN apt-get purge -y --auto-remove \
        build-essential \
        git \
        postgresql-server-dev-16 \
        libreadline-dev \
        zlib1g-dev \
        bison \
        flex

COPY init/ /docker-entrypoint-initdb.d/

# postgres runs as the postgres OS user (non-root) by default