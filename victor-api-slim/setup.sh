#!/bin/bash
# Victor Smart-Kill local API — first-time setup
set -e

echo ""
echo "========================================"
echo " Victor Smart-Kill Local API Setup"
echo "========================================"
echo ""

# Check dependencies
for cmd in docker openssl; do
  if ! command -v $cmd &>/dev/null; then
    echo "[ERROR] $cmd is required but not installed."
    exit 1
  fi
done

# Generate self-signed TLS certificate
if [ ! -f certs/cert.pem ]; then
  echo "[1/2] Generating self-signed TLS certificate..."
  mkdir -p certs
  openssl req -x509 -newkey rsa:2048 \
    -keyout certs/key.pem \
    -out certs/cert.pem \
    -days 3650 -nodes \
    -subj "/CN=local.victorsmartkill.com" \
    -addext "subjectAltName=DNS:local.victorsmartkill.com" \
    2>/dev/null
  echo "    cert.pem and key.pem written to ./certs/"
else
  echo "[1/2] TLS certificate already exists, skipping."
fi

# Remind user to configure .env
echo ""
echo "[2/2] Checking .env configuration..."
if grep -q "your_real_token_here" .env 2>/dev/null; then
  echo ""
  echo "  [!] DEVICE_TOKENS still has placeholder values."
  echo "      Get your real token:"
  echo ""
  echo "      curl -X POST https://www.victorsmarthost.com/api-token-auth/ \\"
  echo "        -H \"Content-Type: application/json\" \\"
  echo "        -d '{\"username\":\"<device_serial>\",\"password\":\"<device_password>\"}'"
  echo ""
  echo "      Then update .env:"
  echo "      DEVICE_TOKENS=<serial>:<token>"
  echo ""
else
  echo "    .env looks configured."
fi

echo ""
echo "========================================"
echo " Setup complete. Start with:"
echo ""
echo "   docker compose up -d"
echo ""
echo " MQTT topics published to your broker:"
echo "   victor/<trap_id>/status        full report on every check-in"
echo "   victor/<trap_id>/battery       battery level %"
echo "   victor/<trap_id>/kills_present true/false"
echo "   victor/<trap_id>/kills_total   lifetime kill count"
echo "   victor/<trap_id>/rssi          WiFi signal strength dBm"
echo "   victor/<trap_id>/activity      heartbeat / kill_detected / etc"
echo "   victor/<trap_id>/alert         kill / low battery / error events"
echo ""
echo " Health check:"
echo "   curl -k https://local.victorsmartkill.com/health"
echo "========================================"
echo ""
