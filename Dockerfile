FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    patch \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the full project
COPY . .

# Ensure log directory exists and state is clean
RUN mkdir -p module1/logs && echo '{}' > module1/logs/fault_state.json

COPY supervisord.conf /etc/supervisor/conf.d/thirdpartychaos.conf
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 3000 8080 8090 9000

ENTRYPOINT ["/docker-entrypoint.sh"]
