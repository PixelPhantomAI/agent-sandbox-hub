FROM python:3.11-slim
WORKDIR /app
# curl for debugging and the isolation test script
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY spokes/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY spokes/ .
