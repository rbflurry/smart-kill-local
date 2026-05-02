# Victor Smart-Kill — Local API Server

Run your Victor Smart-Kill WiFi electronic pest traps completely locally, without relying on the Victor cloud service. Reports trap status to your own MQTT broker.

## Background

Victor Smart-Kill WiFi traps (ESP8266 based) report their status to a cloud API at `www.victorsmarthost.com`. This project replaces that cloud endpoint with a self-hosted FastAPI server that publishes trap events to your existing MQTT broker. No cloud dependency, no Node-RED required.

> **Note:** While the original API is currently still live, there is no guarantee it will remain so. This project lets you run everything independently.

## Notes
I am not sure what causes the api-token-auth process. I have been able to reprovision my traps to my self hosted endpoint without the api-token process triggering. 
When it skips that process the trap sends updates to the /trap api endpoint with the token in the headers of the request.

---

## How It Works

The device uses two endpoints:

1. `POST /api-token-auth/` — authenticates with a username and password, expects a bearer token in response
2. `POST /traps/<trap_id>/history/` — sends a status or event report using that token

Both calls are made over **HTTPS**. The device does not validate the SSL certificate, so a self-signed cert works fine.

---

## Prerequisites

- Docker and Docker Compose
- An existing MQTT broker on your network (Mosquitto, EMQX, Home Assistant's built-in broker, etc.)
- A local DNS entry pointing `local.victorsmartkill.com` at your server — the device checks the hostname and will not connect to bare IP addresses
- `openssl` (only needed if running in SSL mode)
- You can choose to capture traffic to the original api (www.victorsmarthost.com) by setting up a local DNS entry for it. This will give you the auth token when the device polls into the traps/history api. The Username of the trap can be found in the mobile app.

---

## Quick Start

```bash
git clone https://github.com/rbflurry/smart-kill-local
cd smart-kill-local

# Configure your environment
cp .env.example .env
nano .env

# Optional: generate a self-signed cert if not using a reverse proxy
chmod +x setup.sh && ./setup.sh

# Start
docker compose up -d
```

---

## Run Modes

### Mode A — Standalone SSL (no reverse proxy)

uvicorn handles TLS directly. Useful if you don't already have a reverse proxy.

In `.env`:
```env
PORT=443
```

In `docker-compose.yml`, uncomment:
```yaml
SSL_CERTFILE: /certs/cert.pem
SSL_KEYFILE:  /certs/key.pem
```

Generate a self-signed cert (or bring your own):
```bash
./setup.sh
# Choose option [1]
```

### Mode B — Behind a reverse proxy (nginx, Caddy, Traefik, etc.)

Run uvicorn on plain HTTP and let your existing reverse proxy handle TLS termination.

In `.env`:
```env
PORT=8080
```

Leave `SSL_CERTFILE` and `SSL_KEYFILE` commented out in `docker-compose.yml`.

Point your reverse proxy at `http://localhost:8080`.

**Example Caddy config:**
```
local.victorsmartkill.com {
    reverse_proxy localhost:8080
    tls /path/to/cert.pem /path/to/key.pem
}
```

**Example nginx config:**
```nginx
server {
    listen 443 ssl;
    server_name local.victorsmartkill.com;
    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    location / {
        proxy_pass http://localhost:8080;
    }
}
```

---

## Local DNS

The device refuses bare IP addresses — `local.victorsmartkill.com` must resolve to your server. Set this up in one of:

- **Pi-hole:** Local DNS → DNS Records
- **Router:** Local DNS override or host record in your router admin page
- **Adguard Home:** Filters → DNS Rewrites

---

## Step-by-Step Device Setup

### 1. Capture device credentials

Each trap has a unique username (its serial number) and password baked into its firmware. The API server publishes these automatically to your MQTT broker the first time a device checks in, so no additional tooling is required.

Provision the device first (see step 2), then subscribe to the credentials topic on your broker:

```bash
mosquitto_sub -h <mqtt_host> -u <mqtt_user> -P <mqtt_pass> \
  -t 'victor/+/credentials' -v
```

When the device wakes and hits `/api-token-auth/` you will see:

```json
{
  "timestamp": "2026-01-01T00:00:00.000000",
  "username": "<device_serial>",
  "password": "<device_password>"
}
```

The topic is published with `retain=true` so you can subscribe at any time after the device has checked in — you don't need to be watching at the exact moment it connects. The credentials will persist on the broker until overwritten.

Save the username and password — they are unique to each physical trap.

### 2. Provision the device

1. Hold the WiFi button at power-up until the **blue LED flashes**
2. The device broadcasts a `VICTOR-XXXXXX` soft-AP WiFi network
3. Connect your laptop or phone to that network
4. Run the provisioning request:

```bash
# Confirm the device is responding
curl http://192.168.1.1/wifiscan

# Send credentials — curl 52 (empty reply) on this request is normal
curl -X POST http://192.168.1.1/ \
  -H "Content-Type: application/json" \
  -d '{
    "ssid":      "YourHomeWiFiSSID",
    "password":  "YourWiFiPassword",
    "trap_host": "local.victorsmartkill.com"
  }'
```

> `trap_host` must be a bare hostname with no `https://` prefix — the firmware prepends that itself.

The device will reboot, connect to your WiFi, and start calling your local server.

### 3. Get the real bearer token

The device validates the token returned by `/api-token-auth/` against a value stored in its firmware. You must return the real token — a locally generated one will be rejected.

While the original API is still live, exchange your device credentials for the real token:

```bash
curl -X POST https://www.victorsmarthost.com/api-token-auth/ \
  -H "Content-Type: application/json" \
  -d '{"username":"<device_serial>","password":"<device_password>"}'
```

Response:
```json
{"token":"<40_character_hex_token>"}
```

Save this token. Add it to your `.env`:

```env
DEVICE_TOKENS=<device_serial>:<device_token>
```

For multiple traps, comma-separate the entries:
```env
DEVICE_TOKENS=<serial_1>:<token_1>,<serial_2>:<token_2>
```

---

## Configuration

All configuration is via environment variables in `.env`:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MQTT_HOST` | Yes | — | IP or hostname of your MQTT broker |
| `MQTT_PORT` | No | `1883` | MQTT broker port |
| `MQTT_USER` | No | — | MQTT username |
| `MQTT_PASS` | No | — | MQTT password |
| `MQTT_PREFIX` | No | `victor` | Topic prefix for all published messages |
| `DEVICE_TOKENS` | Yes | — | Comma-separated `serial:token` pairs |
| `PORT` | No | `8080` | Port uvicorn listens on |
| `SSL_CERTFILE` | No | — | Path to cert — enables SSL mode when set |
| `SSL_KEYFILE` | No | — | Path to key — enables SSL mode when set |

---

## MQTT Topics

All messages are published with `retain=true` and `qos=1`.

| Topic | Payload | Description |
|-------|---------|-------------|
| `victor/<trap_id>/status` | Full report object | Published on every check-in |
| `victor/<trap_id>/battery` | `{"value": 85, "unit": "%"}` | Battery level |
| `victor/<trap_id>/kills_present` | `{"value": false}` | Kill in chamber |
| `victor/<trap_id>/kills_total` | `{"value": 3}` | Lifetime kill count |
| `victor/<trap_id>/rssi` | `{"value": -60, "unit": "dBm"}` | WiFi signal strength |
| `victor/<trap_id>/activity` | `{"value": "heartbeat"}` | Activity label |
| `victor/<trap_id>/alert` | Alert object | Kill, low battery, or error events |

### Full status payload

```json
{
  "timestamp": "2026-05-01T14:52:26.776Z",
  "trap_id": "000000",
  "sequence_number": 185,
  "activity_type": 4,
  "activity_label": "heartbeat",
  "kills_present": false,
  "total_kills_reported": 0,
  "battery_level": 100,
  "wireless_network_rssi": -60,
  "firmware_version": "2.0.17",
  "error_code": 0
}
```

### Alert payload

```json
{
  "timestamp": "2026-05-01T14:52:26.776Z",
  "type": "kill_detected",
  "message": "Trap 000000 detected a kill"
}
```

---

## Activity Types

| Value | Label | Description |
|-------|-------|-------------|
| `1` | `power_on` | First boot report |
| `2` | `wifi_button_wake` | WiFi button held at power-up |
| `3` | `deep_sleep_wake` | Scheduled wake from deep sleep |
| `4` | `heartbeat` | Periodic status check-in |
| `5` | `kill_detected` | Pest detected, kill initiated |
| `6` | `needs_cleaning` | Kill confirmed, trap needs emptying |
| `7` | `kill_cleaned` | Trap emptied and reset |

---

## Testing Without a Physical Trap

```bash
# Heartbeat
curl -k -X POST https://local.victorsmartkill.com/traps/000000/history/ \
  -H "Content-Type: application/json" \
  -H "Authorization: token <your_token>" \
  -d '{"sequence_number":"1","activity_type":"4","kills_present":"0","total_kills_reported":"0","battery_level":"100","wireless_network_rssi":"-60","firmware_version_string":"2.0.17","error_code":"0"}'

# Kill detected
curl -k -X POST https://local.victorsmartkill.com/traps/000000/history/ \
  -H "Content-Type: application/json" \
  -H "Authorization: token <your_token>" \
  -d '{"sequence_number":"2","activity_type":"5","kills_present":"1","total_kills_reported":"1","battery_level":"98","wireless_network_rssi":"-60","firmware_version_string":"2.0.17","error_code":"0"}'

# Low battery
curl -k -X POST https://local.victorsmartkill.com/traps/000000/history/ \
  -H "Content-Type: application/json" \
  -H "Authorization: token <your_token>" \
  -d '{"sequence_number":"3","activity_type":"4","kills_present":"0","total_kills_reported":"0","battery_level":"15","wireless_network_rssi":"-60","firmware_version_string":"2.0.17","error_code":"0"}'
```

---

## Health Check

```bash
curl [-k] http[s]://local.victorsmartkill.com/health
```

```json
{"status": "ok", "timestamp": "2026-05-01T14:52:26.776Z"}
```

---

## Known Limitations

- **Bearer token is device-specific and validated on-device.** The device checks the token returned by `/api-token-auth/` against a value stored in its firmware. You must return the real token obtained from `www.victorsmarthost.com`. An arbitrary string will cause the device to retry 3 times then go back to deep sleep.
- **Hostname must match `*.victorsmartkill.com`.** The device refuses bare IP addresses and non-matching hostnames.
- **HTTPS required/443** The device uses BearSSL for TLS but does not validate the certificate. A self-signed cert is sufficient.

---

## Roadmap

- [ ] Ghidra firmware analysis to locate and patch the token validation check
- [ ] Patched firmware that accepts any token from a local server (removes cloud dependency entirely)
- [ ] ESPHome firmware replacement
- [ ] Home Assistant MQTT auto-discovery config

---

## Firmware Details

For those interested in the underlying hardware — the device is ESP8266 based with a 4MB flash. The firmware image has the following memory layout:

| Segment | Load Address | Size | Region |
|---------|-------------|------|--------|
| 0 | `0x40201010` | 397 KB | IROM — main application code |
| 1 | `0x40100000` | 232 B | IRAM |
| 2 | `0x401000e8` | 27 KB | IRAM |
| 3 | `0x3ffe8000` | 1.4 KB | DRAM |
| 4 | `0x3ffe8580` | 4.8 KB | DRAM |

Entry point: `0x401000b8`

To analyse in Ghidra use processor **Xtensa:LE:32:default** and load each segment via Window → Memory Map → Add at the addresses above. The token validation function can be found by searching strings for `Invalid token` and following references.

---

## Disclaimer

This project is for personal use on devices you own. Do not use this project to access traps you do not own.
