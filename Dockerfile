FROM python:3.12-slim
WORKDIR /app
COPY bot/requirements.txt bot/requirements.txt
RUN pip install --no-cache-dir -r bot/requirements.txt
COPY bot/ bot/
# config.yaml, state/ e logs/ vêm do volume (ver docker-compose.yml)
CMD ["python", "-m", "bot.run", "--config", "bot/config.yaml"]
