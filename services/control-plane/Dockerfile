# Zeropark Control Plane — internal service, NEVER include in client deliveries.
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8090
CMD ["uvicorn", "zeropark_control.main:app", "--host", "0.0.0.0", "--port", "8090"]
