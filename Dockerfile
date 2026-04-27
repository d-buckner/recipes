# ── Stage 1: Build the frontend ──────────────────────────────────────────────
FROM node:22-slim AS frontend
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

# ── Stage 2: Python application ───────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

RUN useradd --system --no-create-home --shell /usr/sbin/nologin recipes

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

COPY --from=frontend /ui/dist ./ui/dist

RUN mkdir /data && chown recipes:recipes /data

USER recipes

VOLUME ["/data"]

ENV RECIPES_DB_PATH=/data/recipes.db
ENV RECIPES_STATIC_DIR=/app/ui/dist

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/stats')"

CMD ["recipes", "serve", "--host", "0.0.0.0"]
