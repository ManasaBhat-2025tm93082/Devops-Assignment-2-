# ---------- Stage 1: runtime image ----------
FROM python:3.12-slim AS base
ARG APP_VERSION=1.0.0
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    ACEEST_DB=/data/aceest_fitness.db \
    APP_VERSION=${APP_VERSION}
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY templates/ templates/
# Run as non-root user
RUN useradd --create-home appuser && mkdir /data && chown appuser /data
USER appuser
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]

# ---------- Stage 2: test image (adds pytest + tests) ----------
FROM base AS test
USER root
COPY requirements-dev.txt pytest.ini ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests/ tests/
USER appuser
CMD ["pytest", "-v"]
