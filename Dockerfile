FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# install system dependencies for OCRmyPDF and Tesseract OCR + rsync for seeding
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       pngquant \
       jbig2 \
       unpaper \
       tesseract-ocr tesseract-ocr-eng tesseract-ocr-nor \
       poppler-utils qpdf ghostscript \
       rsync ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY web/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy core library and web app into container root (/app)
COPY nbno.py ./
COPY web/app.py ./
COPY web/static ./static
COPY web/templates ./templates

# /data for downloads and logs, /opt/tessdata to allow user added ocr models
VOLUME ["/data", "/opt/tessdata"]
ENV DOWNLOAD_DIR=/data

# Expose web port
EXPOSE 5000

# Make entrypoint available
COPY web/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Default to running the app; entrypoint will seed tessdata first
ENTRYPOINT ["entrypoint.sh"]
CMD ["python3", "app.py"]
