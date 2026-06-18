FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Tesseract OCR + языковые пакеты (рус/каз/англ) — приём прайсов сканом/фото.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-rus tesseract-ocr-kaz \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# SQLite-файл и загрузки живут в /data (volume), чтобы переживать пересборку.
ENV DATABASE_URL=sqlite:////data/medtech.db
RUN chmod +x entrypoint.sh

EXPOSE 8000
CMD ["./entrypoint.sh"]
