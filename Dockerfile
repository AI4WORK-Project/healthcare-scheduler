FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/AI4WORK-Project/healthcare-scheduler" \
      org.opencontainers.image.description="Human-Aware Task Planner – Nurse Rostering" \
      org.opencontainers.image.licenses="EPL-2.0"

WORKDIR /app

# Install the dependencies first, so that changing only the code does not
# reinstall them
COPY pyproject.toml /app/
RUN pip install /app/

# Install the healthcare package
COPY LICENSE NOTICE /app/
COPY healthcare/ /app/healthcare/
RUN pip install --no-deps /app/
COPY server.py /app/

# Expose the port of the server
EXPOSE 5000

# Report the container as unhealthy if the server stops answering
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health', timeout=4)"

# Run the server
CMD ["python", "server.py"]
