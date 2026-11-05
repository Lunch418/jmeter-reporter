# syntax=docker/dockerfile:1

# ---- base: runtime dependencies only ----
# Pinned by digest: the build does not change under our feet. Dependabot bumps it.
FROM python:3.15-slim@sha256:8c13a3f37a6a5b71498228e902c4b9f51c1f7900d49fabf71f9a650c6120e0d0 AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TERM=xterm-256color \
    COLORTERM=truecolor \
    HOME=/tmp
WORKDIR /app
# Exact versions with hashes (requirements.lock): reproducible and tamper-evident.
# The image has the interface; tzdata because slim images have no system time zones.
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY *.py report.example.toml docker-entrypoint.sh ./
COPY jmeter_reporter/ jmeter_reporter/
COPY tools/ tools/
COPY samples/ samples/
RUN chmod +x docker-entrypoint.sh

# ---- test: runtime + pytest, `docker build --target test .` runs the suite ----
FROM base AS test
COPY requirements.txt requirements-tui.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY README.md CHANGELOG.md ./
COPY docs/ docs/
COPY tests/ tests/
RUN python -m pytest -q

# ---- runtime (default target) ----
FROM base AS runtime
# Work on mounted data: docker run -it -v "$PWD:/data" ...
VOLUME /data
WORKDIR /data
# Not root: files created in /data belong to the caller. Run with --user "$(id -u):$(id -g)"
# so the mounted folder is writable (report.sh and docker-compose.yml already do this).
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER app
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["tui"]
