# Dockerfile for VRC_Banking_System_Backend
FROM python:3.13-slim
WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY . /app/

# Install dependencies as root (uv pip install --system requires root)
RUN uv pip install --system --no-cache -r requirements.txt

# Create non-root user and transfer ownership
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

USER appuser

# Initialize database as appuser so the DB file is owned by the user
RUN python -c "from Utils import DbManager; DbManager.initialize_users_db()"

CMD ["python", "VRC_Banking_System_Backend_Server.py"]
