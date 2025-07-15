FROM python:3.11-slim

WORKDIR /app

# Install dependencies sistem yang dibutuhkan untuk matplotlib, pandas_ta, dll
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    libfreetype6-dev \
    libpng-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt

COPY bot.py .

CMD ["python", "bot.py"]
