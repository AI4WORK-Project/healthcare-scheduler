FROM python:3.10

WORKDIR /app

COPY pyproject.toml /app/
COPY healthcare/ /app/healthcare/
COPY server.py /app/

# Install the healthcare package and dependencies
RUN pip install /app/

# Expose the port of the server
EXPOSE 5000

# Run the server
CMD ["python", "server.py"]
