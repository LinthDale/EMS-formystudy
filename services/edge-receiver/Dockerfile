FROM python:3.11-slim
WORKDIR /app
COPY services/edge-receiver/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY services/delta/delta_device ./delta_device
COPY services/edge-receiver/edge_receiver ./edge_receiver
RUN useradd --uid 10001 --create-home receiver
USER receiver
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "edge_receiver.receiver"]
