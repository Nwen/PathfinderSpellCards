# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Build-time deps (gcc needed for cffi/lxml native extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

# Minimal stub so hatchling can resolve the package during dep install
RUN mkdir -p src && touch src/__init__.py

RUN pip install --no-cache-dir .

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="Pathfinder Spell Cards" \
      org.opencontainers.image.description="Générateur de cartes de sorts Pathfinder 1e" \
      org.opencontainers.image.licenses="MIT"

# System deps for WeasyPrint (Cairo, Pango, GDK-Pixbuf) + curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    shared-mime-info \
    fonts-liberation \
    fontconfig \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -fv

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Application code (PYTHONPATH=/app makes "src" resolve to /app/src, taking
# precedence over the stub installed in site-packages)
COPY src/ ./src/
COPY scripts/ ./scripts/

VOLUME ["/app/data"]

ENV PORT=8974 \
    BASE_URL="http://localhost:8974" \
    DATABASE_URL="sqlite:////app/data/spells.db" \
    DATA_DIR="/app/data" \
    PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["sh", "-c", "python -m uvicorn src.main:app --host 0.0.0.0 --port ${PORT}"]
