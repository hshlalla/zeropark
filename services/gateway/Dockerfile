FROM python:3.12-slim

WORKDIR /app

# Product workspace only (engines are native; external/ is reference-only and not copied).
COPY packages/zeropark-core /app/packages/zeropark-core
COPY packages/zeropark-engines /app/packages/zeropark-engines
COPY services/gateway /app/services/gateway

# Install Docker CLI, Node.js (for MCP servers), and LibreOffice (for PPTX to PDF conversion)
RUN apt-get update && apt-get install -y docker.io curl nodejs npm libreoffice-core libreoffice-impress && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    -e packages/zeropark-core \
    -e packages/zeropark-engines \
    -e services/gateway

EXPOSE 8080

CMD ["uvicorn", "zeropark_gateway.main:app", "--host", "0.0.0.0", "--port", "8080"]
