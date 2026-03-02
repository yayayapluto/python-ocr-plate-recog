# ── Stage 1: base with system deps ───────────────────────────────────────────
FROM python:3.11-slim AS base

# OpenCV needs these at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Stage 2: install Python deps ─────────────────────────────────────────────
FROM base AS deps

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Stage 3: final image ──────────────────────────────────────────────────────
FROM deps AS final

COPY app/ ./app/

# Directory where Go API writes entry photos via shared Docker volume
RUN mkdir -p /mnt/storage/photos

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
