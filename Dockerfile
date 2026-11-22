FROM python:3.12-slim

WORKDIR /app

COPY . .

ENV AGENT_PORT=8765 \
    AGENT_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1

EXPOSE 8765

VOLUME ["/app/agent/data"]

CMD ["python", "agent/server.py"]
