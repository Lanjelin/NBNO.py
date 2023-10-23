FROM python:3.12.0-alpine3.18

COPY requirements.txt /app/
COPY nbno.py /app/

RUN \
  python3 -m pip install -r /app/requirements.txt

VOLUME /data
WORKDIR /data
ENTRYPOINT ["python3", "/app/nbno.py"]
