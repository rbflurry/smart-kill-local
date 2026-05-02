#!/bin/bash
# Victor Smart-Kill local API — optional SSL setup
# Only needed if running in SSL mode (not behind a reverse proxy)
set -e

echo ""
echo "========================================"
echo " Victor Smart-Kill Local API Setup"
echo "========================================"
echo ""

for cmd in docker openssl; do
  if ! command -v $cmd &>/dev/null; then
    echo "[ERROR] $cmd is required but not installed."
    exit 1
  fi
done

echo "Run mode:"
echo "  [1] SSL mode     — uvicorn serves HTTPS directly on port 443"
echo "  [2] Proxy mode   — plain HTTP, your reverse proxy handles TLS"
echo ""
read -rp "Choose [1/2]: " MODE

if [ "$MODE" = "1" ]; then
  if [ ! -f certs/cert.pem ]; then
    echo ""
    echo "Generating self-signed TLS certificate..."
    mkdir -p certs
    openssl req -x509 -newkey rsa:2048 \
      -keyout certs/key.pem \
      -out certs/cert.pem \
      -days 3650 -nodes \
      -subj "/CN=local.victorsmartkill.com" \
      -addext "subjectAltName=DNS:local.victorsmartkill.com" \
      2>/dev/null
    echo "  certs/cert.pem and certs/key.pem generated."
  else
    echo "  Certificate already exists, skipping."
  fi

  echo ""
  echo "Uncomment these lines in docker-compose.yml:"
  echo "  SSL_CERTFILE: /certs/cert.pem"
  echo "  SSL_KEYFILE:  /certs/key.pem"
  echo ""
  echo "And set PORT=443 in .env"

else
  echo ""
  echo "Proxy mode selected."
  echo "Point your reverse proxy at http://localhost:\${PORT} (default 8080)."
  echo "The device requires the hostname local.victorsmartkill.com to resolve"
  echo "to your proxy, which should terminate TLS and forward to this container."
fi

echo ""
echo "========================================"
echo ""

if grep -q "<device_serial>" .env 2>/dev/null; then
  echo " [!] DEVICE_TOKENS in .env still has placeholder values."
  echo ""
  echo "     Provision your trap once to capture its credentials, then run:"
  echo ""
  echo "     curl -X POST https://www.victorsmarthost.com/api-token-auth/ \\"
  echo "       -H \"Content-Type: application/json\" \\"
  echo "       -d '{\"username\":\"<serial>\",\"password\":\"<password>\"}'"
  echo ""
  echo "     Add the result to .env:"
  echo "     DEVICE_TOKENS=<serial>:<token>"
  echo ""
fi

echo " Start with:  docker compose up -d"
echo " Health:      curl [-k] https[http]://localhost:\${PORT}/health"
echo "========================================"
echo ""
