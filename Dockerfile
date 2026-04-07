FROM python:3.11-slim
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-noto \
    fonts-noto-cjk \
    fonts-noto-extra \
    fontconfig \
    && fc-cache -f -v \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "main:app", "--timeout", "300", "--workers", "1", "--bind", "0.0.0.0:8080"]
