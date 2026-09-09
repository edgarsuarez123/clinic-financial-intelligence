FROM python:3.12-slim
WORKDIR /srv/clinic
COPY pyproject.toml requirements.lock ./
COPY app ./app
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home clinic
COPY migrations ./migrations
COPY ui ./ui
COPY config/simulation-example.json ./config/simulation-example.json
USER clinic
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers"]
