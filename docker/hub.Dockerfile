FROM python:3.11-slim
WORKDIR /app
COPY hub/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copy hub/ contents to /app AND preserve as hub/ package for imports
COPY hub/ ./hub/
# server.py must be at /app root
RUN cp hub/server.py .
ENV SANDBOX_BASE=/sandbox
CMD ["python", "server.py"]
