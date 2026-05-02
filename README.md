# Victor Smart-Kill — Local API Server

Run your Victor Smart-Kill electronic pest trap completely locally using Node-RED, without relying on the Victor cloud service.

## Background

The Victor Smart-Kill WiFi traps (ESP8266 based) report their status to a cloud API at `www.victorsmarthost.com`. This project replaces that cloud endpoint with a self-hosted Node-RED server, giving you full local control and visibility over your traps.

> **Note:** While the original API is currently still live, there is no guarantee it will remain so. This guide lets you run everything independently.

---

## How It Works

The device follows a simple two-step protocol on every wake cycle:

1. `POST /api-token-auth/` — authenticates with a username and password, expects a bearer token in response
2. `POST /traps/<trap_id>/history/` — sends a status/event report using that token

Both calls are made over **HTTPS**. The device does not validate the SSL certificate, so a self-signed cert works fine.

---

## Prerequisites

- Node-RED running on a local machine
- HTTPS on port 443 pointing at Node-RED — either via nginx/Caddy reverse proxy or Node-RED's built-in HTTPS in `settings.js`
- A local DNS entry pointing `local.victorsmartkill.com` at your Node-RED machine (the device checks the hostname and will not connect to bare IP addresses)
- `openssl` for generating a self-signed certificate

---

## Step 1 — Set Up HTTPS

The device requires HTTPS. Generate a self-signed certificate with the correct hostname:

```bash
openssl req -x509 -newkey rsa:2048 \
  -keyout key.pem -out cert.pem \
  -days 3650 -nodes \
  -subj "/CN=local.victorsmartkill.com" \
  -addext "subjectAltName=DNS:local.victorsmartkill.com"
```

### Option A — nginx reverse proxy (recommended)

```nginx
server {
    listen 443 ssl;
    server_name local.victorsmartkill.com;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:1880;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
}
```

### Option B — Node-RED built-in HTTPS

In your Node-RED `settings.js`:

```js
https: {
    key:  require("fs").readFileSync('/path/to/key.pem'),
    cert: require("fs").readFileSync('/path/to/cert.pem'),
},
```

---

## Step 2 — Local DNS

The device will refuse to connect to a bare IP address. You must point `local.victorsmartkill.com` at your Node-RED machine using one of:

- **Pi-hole:** Local DNS → DNS Records → add `local.victorsmartkill.com` → your server IP
- **Router:** Add a local DNS override or host record in your router admin page
- **hosts file** on your server (only resolves locally, not for the device itself)

---

## Step 3 — Get Your Device Credentials and Bearer Token

Each device has a unique username and password baked into its firmware. Before the original API goes away, capture your device's credentials and exchange them for a bearer token.

### 3a — Capture credentials with Node-RED

Import this flow to intercept the device's auth request and log its credentials:

```json
[
  {
    "id": "capture-tab",
    "type": "tab",
    "label": "Credential Capture"
  },
  {
    "id": "http-in-capture",
    "type": "http in",
    "z": "capture-tab",
    "name": "POST /api-token-auth/",
    "url": "/api-token-auth/",
    "method": "post",
    "x": 160,
    "y": 100,
    "wires": [["fn-capture", "log-capture"]]
  },
  {
    "id": "fn-capture",
    "type": "function",
    "z": "capture-tab",
    "name": "Log and hold",
    "func": "node.warn('=== DEVICE CREDENTIALS ===');\nnode.warn('Username: ' + msg.payload.username);\nnode.warn('Password: ' + msg.payload.password);\nflow.set('device_username', msg.payload.username);\nflow.set('device_password', msg.payload.password);\nmsg.statusCode = 200;\nmsg.headers = { 'Content-Type': 'application/json', 'Content-Length': 2, 'Connection': 'close' };\nmsg.payload = '{}';\nreturn msg;",
    "outputs": 1,
    "x": 380,
    "y": 100,
    "wires": [["http-out-capture"]]
  },
  {
    "id": "http-out-capture",
    "type": "http response",
    "z": "capture-tab",
    "name": "",
    "x": 580,
    "y": 100,
    "wires": []
  },
  {
    "id": "log-capture",
    "type": "debug",
    "z": "capture-tab",
    "name": "Raw auth payload",
    "active": true,
    "complete": "payload",
    "x": 380,
    "y": 160,
    "wires": []
  }
]
```

Provision the device (see Step 4) with `trap_host` set to `local.victorsmartkill.com`. When it wakes and calls home you will see its credentials in the Node-RED debug panel:

```
Username: WM201027GV00000
Password: FK9BKL00000
```

> **Save these.** They are unique to each physical device and are stored in the device firmware.

### 3b — Exchange credentials for a bearer token

While the original API is still live, get the real bearer token for your device:

```bash
curl -X POST https://www.victorsmarthost.com/api-token-auth/ \
  -H "Content-Type: application/json" \
  -d '{"username":"WM201027GV00000","password":"FK9BKL00000"}'
```

Response:

```json
{"token":"yourdevicetoken"}
```

> **Save this token.** The device validates the token value against what it expects. Until the firmware is patched or replaced, you must return this exact token from your local server.

---

## Step 4 — Provision the Device

Provisioning points the device at your local server instead of the Victor cloud.

1. Hold the WiFi button at power-up until the **blue LED flashes**
2. The device broadcasts a `VICTOR-XXXXXX` WiFi soft-AP network
3. Connect your laptop or phone to that network
4. Run the provisioning script below, or use curl

### Provisioning script

```bash
# Step 1 — confirm device is responding
curl http://192.168.4.1/wifiscan

# Step 2 — send credentials
curl -X POST http://192.168.4.1/ \
  -H "Content-Type: application/json" \
  -d '{
    "ssid":      "YourHomeWiFiSSID",
    "password":  "YourWiFiPassword",
    "trap_host": "local.victorsmartkill.com"
  }'
```

The device will accept the payload, reboot, connect to your WiFi, and start calling your Node-RED server. The device closes the connection immediately after receiving credentials.

> **trap_host format:** bare hostname only, no `https://` prefix. The firmware prepends that itself.
> **IP Address** The Trap IP address might be 192.168.1.1, check to see what IP address to use when your laptop joins the standalone ap.

---

## Step 5 — Node-RED Main Flow

Import this flow to handle authentication and trap reporting. Replace the token value with your real token captured in Step 3b.

```json
[
  {
    "id": "victor-tab",
    "type": "tab",
    "label": "Victor Smart-Kill API"
  },
  {
    "id": "http-in-auth",
    "type": "http in",
    "z": "victor-tab",
    "name": "POST /api-token-auth/",
    "url": "/api-token-auth/",
    "method": "post",
    "x": 160,
    "y": 100,
    "wires": [["fn-auth", "log-auth"]]
  },
  {
    "id": "fn-auth",
    "type": "function",
    "z": "victor-tab",
    "name": "Return real token",
    "func": "node.warn('Auth request - user: ' + (msg.payload.username || ''));\nvar body = '{\"token\":\"YOUR_REAL_TOKEN_HERE\"}';\nmsg.statusCode = 200;\nmsg.headers = {\n    'Content-Type': 'application/json',\n    'Content-Length': body.length,\n    'Connection': 'close'\n};\nmsg.payload = body;\nreturn msg;",
    "outputs": 1,
    "x": 390,
    "y": 100,
    "wires": [["http-out-auth"]]
  },
  {
    "id": "http-out-auth",
    "type": "http response",
    "z": "victor-tab",
    "name": "",
    "x": 590,
    "y": 100,
    "wires": []
  },
  {
    "id": "log-auth",
    "type": "debug",
    "z": "victor-tab",
    "name": "Auth log",
    "active": true,
    "complete": "payload",
    "x": 380,
    "y": 160,
    "wires": []
  },
  {
    "id": "http-in-history",
    "type": "http in",
    "z": "victor-tab",
    "name": "POST /traps/:id/history/",
    "url": "/traps/:id/history/",
    "method": "post",
    "x": 160,
    "y": 300,
    "wires": [["fn-history", "log-history-raw"]]
  },
  {
    "id": "fn-history",
    "type": "function",
    "z": "victor-tab",
    "name": "Parse trap report",
    "func": "var p = msg.payload || {};\nvar trapId = msg.req.params.id;\n\nvar report = {\n    timestamp:              new Date().toISOString(),\n    trap_id:                trapId,\n    sequence_number:        p.sequence_number,\n    activity_type:          parseInt(p.activity_type),\n    kills_present:          p.kills_present === '1' || p.kills_present === true,\n    total_kills_reported:   parseInt(p.total_kills_reported),\n    battery_level:          parseInt(p.battery_level),\n    wireless_network_rssi:  parseInt(p.wireless_network_rssi),\n    firmware_version:       p.firmware_version_string,\n    error_code:             parseInt(p.error_code)\n};\n\nvar activityLabels = {\n    1: 'Power on',\n    2: 'WiFi button wake',\n    3: 'Deep sleep wake',\n    4: 'Heartbeat',\n    5: 'Kill detected',\n    6: 'Needs cleaning',\n    7: 'Kill cleaned'\n};\nreport.activity_label = activityLabels[report.activity_type] || 'Unknown';\n\nnode.warn('Trap ' + trapId + ' | ' + report.activity_label +\n    ' | kills: ' + report.total_kills_reported +\n    ' | battery: ' + report.battery_level + '%' +\n    ' | rssi: ' + report.wireless_network_rssi);\n\nvar history = flow.get('report_history') || [];\nhistory.unshift(report);\nif (history.length > 100) history = history.slice(0, 100);\nflow.set('report_history', history);\nflow.set('last_report', report);\n\nmsg.statusCode = 204;\nmsg.headers = { 'Connection': 'close' };\nmsg.payload = '';\nmsg.report = report;\n\nnode.send([msg, { payload: report }]);\nreturn null;",
    "outputs": 2,
    "x": 390,
    "y": 300,
    "wires": [["http-out-history"], ["log-history-parsed", "fn-alerts"]]
  },
  {
    "id": "http-out-history",
    "type": "http response",
    "z": "victor-tab",
    "name": "204 No Content",
    "statusCode": "204",
    "x": 620,
    "y": 260,
    "wires": []
  },
  {
    "id": "log-history-raw",
    "type": "debug",
    "z": "victor-tab",
    "name": "Raw payload",
    "active": true,
    "complete": "payload",
    "x": 370,
    "y": 380,
    "wires": []
  },
  {
    "id": "log-history-parsed",
    "type": "debug",
    "z": "victor-tab",
    "name": "Parsed report",
    "active": true,
    "complete": "payload",
    "x": 620,
    "y": 300,
    "wires": []
  },
  {
    "id": "fn-alerts",
    "type": "function",
    "z": "victor-tab",
    "name": "Alerts",
    "func": "var r = msg.payload;\nvar alerts = [];\n\nif (r.kills_present) {\n    alerts.push({ type: 'KILL', message: 'Trap ' + r.trap_id + ' has a kill — needs emptying' });\n}\nif (r.battery_level < 20) {\n    alerts.push({ type: 'BATTERY', message: 'Trap ' + r.trap_id + ' battery low: ' + r.battery_level + '%' });\n}\nif (r.error_code !== 0) {\n    alerts.push({ type: 'ERROR', message: 'Trap ' + r.trap_id + ' error code: ' + r.error_code });\n}\n\nif (alerts.length > 0) {\n    msg.payload = alerts;\n    return msg;\n}\nreturn null;",
    "outputs": 1,
    "x": 620,
    "y": 340,
    "wires": [["log-alerts"]]
  },
  {
    "id": "log-alerts",
    "type": "debug",
    "z": "victor-tab",
    "name": "⚠️ Alerts",
    "active": true,
    "complete": "payload",
    "tosidebar": true,
    "tostatus": true,
    "x": 800,
    "y": 340,
    "wires": []
  }
]
```

---

## Activity Types

| Value | Meaning |
|-------|---------|
| `1` | Power on / first boot |
| `2` | WiFi button wake (provisioning triggered) |
| `3` | Deep sleep wake (scheduled check-in) |
| `4` | Periodic heartbeat |
| `5` | Pest detected / kill initiated |
| `6` | Kill detected, needs cleaning |
| `7` | Kill cleaned / trap reset |

---

## Payload Reference

Full list of fields sent by the device on every history report:

| Field | Type | Description |
|-------|------|-------------|
| `sequence_number` | string | Incremental report counter |
| `activity_type` | string | Event type (see table above) |
| `kills_present` | string | `"1"` if a kill is in the chamber |
| `total_kills_reported` | string | Lifetime kill count |
| `battery_level` | string | Battery percentage 0–100 |
| `wireless_network_rssi` | string | WiFi signal strength in dBm |
| `firmware_version_string` | string | Device firmware version |
| `error_code` | string | `"0"` = no error |

---

## Testing Without a Physical Trap

Use curl to simulate any trap event against your Node-RED server:

```bash
# Heartbeat
curl -k -X POST https://local.victorsmartkill.com/traps/242000/history/ \
  -H "Content-Type: application/json" \
  -H "Authorization: token YOUR_REAL_TOKEN_HERE" \
  -d '{"sequence_number":"186","activity_type":"4","kills_present":"0","total_kills_reported":"0","battery_level":"100","wireless_network_rssi":"-60","firmware_version_string":"2.0.17","error_code":"0"}'

# Kill detected
curl -k -X POST https://local.victorsmartkill.com/traps/242000/history/ \
  -H "Content-Type: application/json" \
  -H "Authorization: token YOUR_REAL_TOKEN_HERE" \
  -d '{"sequence_number":"187","activity_type":"5","kills_present":"1","total_kills_reported":"1","battery_level":"98","wireless_network_rssi":"-60","firmware_version_string":"2.0.17","error_code":"0"}'

# Needs cleaning
curl -k -X POST https://local.victorsmartkill.com/traps/242000/history/ \
  -H "Content-Type: application/json" \
  -H "Authorization: token YOUR_REAL_TOKEN_HERE" \
  -d '{"sequence_number":"188","activity_type":"6","kills_present":"1","total_kills_reported":"1","battery_level":"97","wireless_network_rssi":"-60","firmware_version_string":"2.0.17","error_code":"0"}'

# Kill cleaned
curl -k -X POST https://local.victorsmartkill.com/traps/242000/history/ \
  -H "Content-Type: application/json" \
  -H "Authorization: token YOUR_REAL_TOKEN_HERE" \
  -d '{"sequence_number":"189","activity_type":"7","kills_present":"0","total_kills_reported":"1","battery_level":"97","wireless_network_rssi":"-60","firmware_version_string":"2.0.17","error_code":"0"}'

# Low battery
curl -k -X POST https://local.victorsmartkill.com/traps/242000/history/ \
  -H "Content-Type: application/json" \
  -H "Authorization: token YOUR_REAL_TOKEN_HERE" \
  -d '{"sequence_number":"190","activity_type":"4","kills_present":"0","total_kills_reported":"0","battery_level":"15","wireless_network_rssi":"-60","firmware_version_string":"2.0.17","error_code":"0"}'
```

---

## Known Limitations

- **Bearer token is device-specific and validated on the device.** The device checks the token returned by `/api-token-auth/` against a value stored in its firmware. You must return the real token obtained from `www.victorsmarthost.com`. A random string will cause the device to retry 3 times and go back to sleep.
- **Hostname must match `*.victorsmartkill.com`.** The device refuses bare IP addresses and non-matching hostnames. Use a local DNS override to point a subdomain at your server.
- **HTTPS required.** The device uses BearSSL for TLS but does not validate the certificate. A self-signed cert is sufficient.

---

## Roadmap

- [ ] Ghidra firmware analysis to locate and patch the token validation check
- [ ] Patched firmware that accepts any token from a local server
- [ ] ESPHome firmware replacement with full GPIO map
- [ ] Multi-trap support with per-device token management
- [ ] Home Assistant MQTT integration

---

## Firmware Analysis

For those interested in going deeper, the flash dump is an ESP8266 image with the following memory layout:

| Segment | Load Address | Size | Region |
|---------|-------------|------|--------|
| 0 | `0x40201010` | 397 KB | IROM — main app code |
| 1 | `0x40100000` | 232 B | IRAM |
| 2 | `0x401000e8` | 27 KB | IRAM |
| 3 | `0x3ffe8000` | 1.4 KB | DRAM |
| 4 | `0x3ffe8580` | 4.8 KB | DRAM |

Entry point: `0x401000b8`

Load the segments into Ghidra using **Xtensa:LE:32:default** processor, one segment at a time via Window → Memory Map → Add, using the load addresses above. The token validation function can be found by searching strings for `Invalid token` and following references.

---

## Disclaimer

This project is for personal use on devices you own. Device credentials extracted from your own flash dump are your own data. Do not use this project to access traps you do not own.
