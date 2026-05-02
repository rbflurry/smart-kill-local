#!/bin/sh
# Start uvicorn with or without SSL depending on environment variables.
#
# SSL mode:    set SSL_CERTFILE and SSL_KEYFILE to paths of your cert/key
# Proxy mode:  leave SSL_CERTFILE unset — uvicorn runs plain HTTP on PORT
#              and your reverse proxy handles TLS termination

PORT="${PORT:-8080}"

if [ -n "$SSL_CERTFILE" ] && [ -n "$SSL_KEYFILE" ]; then
  echo "[victor-api] Starting with SSL on port $PORT"
  exec uvicorn main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --ssl-certfile "$SSL_CERTFILE" \
    --ssl-keyfile  "$SSL_KEYFILE"
else
  echo "[victor-api] Starting without SSL on port $PORT (reverse proxy mode)"
  exec uvicorn main:app \
    --host 0.0.0.0 \
    --port "$PORT"
fi
