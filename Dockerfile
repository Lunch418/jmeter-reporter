# syntax=docker/dockerfile:1

# ---- base: runtime dependencies only ----
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TERM=xterm-256color \
    COLORTERM=truecolor \
    HOME=/tmp
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY convert.py verify.py preview.py tui.py docker-entrypoint.sh ./
COPY tools/ tools/
COPY samples/ samples/
RUN chmod +x docker-entrypoint.sh

# ---- test: runtime + pytest, `docker build --target test .` runs the suite ----
FROM base AS test
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests/ tests/
RUN python -m pytest -q

# ---- runtime (default target) ----
FROM base AS runtime
# Work on mounted data: docker run -it -v "$PWD:/data" ...
VOLUME /data
WORKDIR /data
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["tui"]
