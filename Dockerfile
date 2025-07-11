FROM python:3.11-slim

# Set working directory inside container to /app
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy whole project into /app
COPY . .

# Tell Python to look in /app for modules
ENV PYTHONPATH=/app

# Run FastAPI app: from /app, find app.main:app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
