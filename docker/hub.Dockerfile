FROM python:3.11-slim
WORKDIR /app
COPY hub/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY hub/ .
ENV SANDBOX_BASE=/sandbox
CMD ["python", "server.py"]
