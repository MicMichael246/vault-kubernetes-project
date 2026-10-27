FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

RUN useradd --system --uid 10001 --create-home appuser

COPY app/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY --chown=appuser:appuser app/app.py /app/app.py

USER 10001:10001

EXPOSE 8080

CMD ["python", "/app/app.py"]
