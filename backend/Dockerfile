FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (needed for psycopg2, PyMuPDF, etc.)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -U -u 1000 appuser && chown -R 1000:1000 /app
USER 1000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9432"]
