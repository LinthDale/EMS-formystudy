FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY delta_device ./delta_device
RUN useradd --uid 10001 --create-home delta && mkdir /data && chown delta:delta /data
USER delta
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "delta_device"]
