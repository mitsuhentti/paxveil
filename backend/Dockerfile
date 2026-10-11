FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_NO_CACHE=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
RUN useradd --uid 10001 --create-home paxveil && mkdir /app/runtime && chown paxveil:paxveil /app/runtime
COPY --chown=paxveil:paxveil . .
USER 10001
EXPOSE 8000
CMD ["uvicorn", "paxveil.api:app", "--host", "0.0.0.0", "--port", "8000"]
