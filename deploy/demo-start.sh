#!/bin/sh
# Start-up for the online demo (Render). Never used at the restaurant.
#
# 1. Tables, roles and settings; the menu if it is empty.
# 2. The server starts straight away, so the page opens quickly.
# 3. Half a minute later, made-up trade is topped up to the current time in
#    the background (app/demo_data.py refuses to run unless ENVIRONMENT=demo).
set -e
cd /srv/backend
python -m app.seed
python -m app.seed_menu || true
( sleep 30; python -m app.demo_data > /tmp/demo-data.log 2>&1 || cat /tmp/demo-data.log ) &
exec python run_server.py --host 0.0.0.0 --port "${PORT:-8000}"
