FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps . \
    && useradd --create-home --uid 10001 astra \
    && mkdir /app/state && chown astra:astra /app/state
COPY configs ./configs
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh
USER astra
# Mode and state come from the environment so the healthcheck and the served
# process can never inspect different files.
ENV ASTRA_MODE=observe ASTRA_STATE=/app/state/observe.db
HEALTHCHECK --interval=60s --start-period=180s --timeout=10s --retries=3 \
    CMD astra health --state "$ASTRA_STATE"
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD []
