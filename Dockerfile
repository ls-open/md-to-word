# Dockerfile for md-to-word MCP Server
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "md-to-word-docx[mcp]"

ENTRYPOINT ["md-to-word-mcp"]
