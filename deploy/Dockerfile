FROM python:3.13-slim
WORKDIR /srv/testjury
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY config ./config
COPY schemas ./schemas
COPY rubric ./rubric
COPY design ./design
COPY kb_content ./kb_content
COPY alembic.ini ./
RUN useradd --create-home --uid 10001 testjury && mkdir -p data/attachments && chown -R testjury:testjury /srv/testjury
USER testjury
EXPOSE 8000
ENV HOST=0.0.0.0
CMD ["python", "-m", "app.bootstrap"]
