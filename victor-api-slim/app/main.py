import os
import json
import logging
from datetime import datetime

import paho.mqtt.client as mqtt
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("victor-api")

app = FastAPI(title="Victor Smart-Kill Local API")

# --- Config from environment ---
MQTT_HOST   = os.getenv("MQTT_HOST", "192.168.1.100")
MQTT_PORT   = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER   = os.getenv("MQTT_USER", "")
MQTT_PASS   = os.getenv("MQTT_PASS", "")
MQTT_PREFIX = os.getenv("MQTT_PREFIX", "victor")

# Device credentials → token map
# Format in .env: "SERIAL1:TOKEN1,SERIAL2:TOKEN2"
DEVICE_TOKENS_RAW = os.getenv("DEVICE_TOKENS", "")

def build_token_map():
    token_map = {}
    for pair in DEVICE_TOKENS_RAW.split(","):
        parts = pair.strip().split(":")
        if len(parts) == 2:
            token_map[parts[0].strip()] = parts[1].strip()
    return token_map

DEVICE_TOKENS = build_token_map()

ACTIVITY_LABELS = {
    1: "power_on",
    2: "wifi_button_wake",
    3: "deep_sleep_wake",
    4: "heartbeat",
    5: "kill_detected",
    6: "needs_cleaning",
    7: "kill_cleaned",
}


def mqtt_publish(topic: str, payload: dict):
    try:
        client = mqtt.Client()
        if MQTT_USER:
            client.username_pw_set(MQTT_USER, MQTT_PASS)
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=5)
        client.publish(topic, json.dumps(payload), qos=1, retain=True)
        client.disconnect()
        logger.info(f"MQTT → {topic}")
    except Exception as e:
        logger.error(f"MQTT publish failed: {e}")


# ---------------------------------------------------------------------------
# POST /api-token-auth/
# ---------------------------------------------------------------------------
@app.post("/api-token-auth/")
async def auth(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    username = body.get("username", "")
    password = body.get("password", "")
    logger.info(f"Auth request from: {username}")

    token = DEVICE_TOKENS.get(username)
    if not token:
        logger.warning(f"No token configured for device: {username}")
        return JSONResponse(
            status_code=401,
            content={"detail": "No token configured for this device"},
            headers={"Connection": "close"},
        )

    mqtt_publish(f"{MQTT_PREFIX}/{username}/auth", {
        "timestamp": datetime.utcnow().isoformat(),
        "username": username,
        "status": "authenticated",
    })

    return JSONResponse(
        status_code=200,
        content={"token": token},
        headers={"Content-Type": "application/json", "Connection": "close"},
    )


# ---------------------------------------------------------------------------
# POST /traps/{trap_id}/history/
# ---------------------------------------------------------------------------
@app.post("/traps/{trap_id}/history/")
async def history(trap_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    activity_type  = int(body.get("activity_type", 0))
    activity_label = ACTIVITY_LABELS.get(activity_type, "unknown")
    kills_present  = body.get("kills_present") in ("1", 1, True, "true")
    battery        = int(body.get("battery_level", 0))
    rssi           = int(body.get("wireless_network_rssi", 0))
    kills_total    = int(body.get("total_kills_reported", 0))
    sequence       = int(body.get("sequence_number", 0))
    firmware       = body.get("firmware_version_string", "")
    error_code     = int(body.get("error_code", 0))
    now            = datetime.utcnow().isoformat()
    base           = f"{MQTT_PREFIX}/{trap_id}"

    logger.info(
        f"Trap {trap_id} | {activity_label} | "
        f"kills={kills_present} total={kills_total} "
        f"battery={battery}% rssi={rssi}dBm seq={sequence}"
    )

    # Full status
    mqtt_publish(f"{base}/status", {
        "timestamp": now,
        "trap_id": trap_id,
        "sequence_number": sequence,
        "activity_type": activity_type,
        "activity_label": activity_label,
        "kills_present": kills_present,
        "total_kills_reported": kills_total,
        "battery_level": battery,
        "wireless_network_rssi": rssi,
        "firmware_version": firmware,
        "error_code": error_code,
    })

    # Individual sensor topics
    mqtt_publish(f"{base}/battery",        {"value": battery,       "unit": "%"})
    mqtt_publish(f"{base}/rssi",           {"value": rssi,          "unit": "dBm"})
    mqtt_publish(f"{base}/kills_present",  {"value": kills_present})
    mqtt_publish(f"{base}/kills_total",    {"value": kills_total})
    mqtt_publish(f"{base}/activity",       {"value": activity_label})

    # Alerts
    alert_map = {
        5: ("kill_detected",  f"Trap {trap_id} detected a kill"),
        6: ("needs_cleaning", f"Trap {trap_id} needs emptying"),
        7: ("kill_cleaned",   f"Trap {trap_id} has been cleaned and reset"),
    }
    if activity_type in alert_map:
        alert_type, alert_msg = alert_map[activity_type]
        mqtt_publish(f"{base}/alert", {"timestamp": now, "type": alert_type, "message": alert_msg})

    if battery < 20:
        mqtt_publish(f"{base}/alert", {"timestamp": now, "type": "low_battery", "message": f"Trap {trap_id} battery low: {battery}%"})

    if error_code != 0:
        mqtt_publish(f"{base}/alert", {"timestamp": now, "type": "error", "message": f"Trap {trap_id} error code: {error_code}"})

    return Response(status_code=204, headers={"Connection": "close"})


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
