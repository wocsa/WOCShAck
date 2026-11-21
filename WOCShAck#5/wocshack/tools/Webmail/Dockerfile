# Description: Dockerfile for the Webmail service
# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy the current directory contents into the container at /app
COPY ./src /app

# Install any needed packages specified in requirements.txt using uv
RUN uv pip install --system --no-cache -r requirements.txt

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Make port 80 available to the world outside this container
EXPOSE 80

# Run Frontend.py when the container launches
CMD ["python", "Frontend.py"]
