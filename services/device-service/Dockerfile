FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY device_service ./device_service

EXPOSE 8002
CMD ["uvicorn", "device_service.main:app", "--host", "0.0.0.0", "--port", "8002"]