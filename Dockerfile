FROM python:3.11-slim

# Cài Noto fonts (tiếng Việt, CJK, emoji) + curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    fonts-dejavu-core \
    fonts-liberation \
    curl \
    && fc-cache -fv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# HF Space chạy port 7860
EXPOSE 7860

CMD ["gunicorn", "--bind", "0.0.0.0:7860", "--workers", "2", "--timeout", "60", "app:app"]
