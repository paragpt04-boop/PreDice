FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -r -u 10001 -d /nonexistent predice
COPY app ./app
USER 10001
EXPOSE 8097
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8097","--proxy-headers","--forwarded-allow-ips","127.0.0.1"]
