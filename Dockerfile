# Use the full python image to ensure stable repository links
FROM python:3.11

# Updated system dependencies for 2026/Debian Trixie
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade pip and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the AI model so the bot responds in < 5 seconds
RUN python -c "from rembg import new_session; new_session('u2netp')"

COPY . .

CMD ["python", "bot.py"]
