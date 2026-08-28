# SearXNG development image based on Debian (same package set as utils/searxng.sh)
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/searxng-venv/bin:${PATH}" \
    SEARXNG_SETTINGS_PATH="/etc/searxng/settings.yml"

# Official Debian packages from utils/searxng.sh (SEARXNG_PACKAGES_debian)
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-dev \
        python3-babel \
        python3-venv \
        python-is-python3 \
        git \
        build-essential \
        libxslt-dev \
        zlib1g-dev \
        libffi-dev \
        libssl-dev \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/local/searxng

COPY requirements.txt requirements-server.txt ./

RUN python3 -m venv /opt/searxng-venv \
    && /opt/searxng-venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel \
    && /opt/searxng-venv/bin/pip install --no-cache-dir \
        -r requirements.txt \
        -r requirements-server.txt \
        "granian[reload]==2.8.1"

COPY . .

EXPOSE 8889

ENTRYPOINT ["sh", "/usr/local/searxng/container/dev-entrypoint.sh"]
