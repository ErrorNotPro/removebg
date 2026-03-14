# Use the full python image (not slim) to ensure all build tools are present
FROM python:3.11

# Install only the absolutely necessary graphics libraries
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Improve pip reliability
RUN pip install --no-cache-dir --upgrade pip

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-load the AI model during build time
RUN python -c "from rembg import new_session; new_session('u2netp')"

COPY . .

# Railway uses the PORT env variable, but for a bot we just need to run the script
CMD ["python", "bot.py"]
