# Gunakan base image Python
FROM python:3.9-slim

# Install dependency OS untuk build TA-Lib
RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    curl \
    libta-lib0 \
    libta-lib0-dev \
    && rm -rf /var/lib/apt/lists/*

# Install TA-Lib Python wrapper
RUN pip install --no-cache-dir TA-Lib yfinance python-telegram-bot mplfinance pandas matplotlib

# Copy seluruh file project ke container
WORKDIR /app
COPY . /app

# Jalankan main.py saat container start
CMD ["python", "main.py"]
