#!/bin/sh
set -e

# Reset fault state on every container start
echo '{}' > /app/module1/logs/fault_state.json

echo "[TPC] All services starting via supervisord..."
echo "[TPC] Run the demo with:"
echo "[TPC]   docker compose exec app python -X utf8 live_demo.py"
echo ""

exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
