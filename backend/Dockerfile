FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home predice && mkdir /data && chown predice /data
COPY predice ./predice
USER 10001:10001
ENV PREDICE_DB=/data/predice.db
EXPOSE 8080
CMD ["uvicorn","predice.app:app","--host","0.0.0.0","--port","8080","--workers","1"]
