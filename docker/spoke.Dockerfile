FROM python:3.11-slim
WORKDIR /app
COPY spokes/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY spokes/ .
