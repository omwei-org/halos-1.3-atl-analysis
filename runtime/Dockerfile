FROM python:3.12-slim

WORKDIR /app
COPY poc /app/poc
COPY runtime /app/runtime

ENV PYTHONPATH=/app
ENV MAGIC_BOX_HOST=0.0.0.0
ENV MAGIC_BOX_PORT=8080

EXPOSE 8080
CMD ["python", "-m", "runtime.magic_box"]
