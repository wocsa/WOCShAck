# Dockerfile for djangoWocshack_5
FROM python:3.13-slim
WORKDIR /app

# Install system dependencies including Chromium for headless GIF generation
# Chromium is used to render CSS loaders into animated GIF
# previews server-side to protect intellectual property.
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set Chrome/Chromium environment variables for Selenium
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY . .

# Install dependencies using uv
RUN uv pip install --system --no-cache -r requirements.txt

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

CMD ["bash", "-c", "python manage.py migrate --noinput && python setup/setup_webmail.py && python setup/setup_banking.py && python manage.py runserver --insecure 0.0.0.0:8000"]
