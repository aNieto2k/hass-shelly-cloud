"""Constants for the Shelly Cloud integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "shelly_cloud"

# Config entry data
CONF_SERVER_URL = "server_url"
CONF_AUTH_KEY = "auth_key"

# Subentry data
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_CODE = "device_code"
CONF_DEVICE_GEN = "device_gen"
CONF_DEVICE_TYPE = "device_type"
CONF_DEVICE_CHANNELS = "device_channels"

# Options
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)
MIN_SCAN_INTERVAL = timedelta(seconds=10)
MAX_SCAN_INTERVAL = timedelta(seconds=300)

# API
RATE_LIMIT_PER_SECOND = 1
BATCH_SIZE = 10
REQUEST_TIMEOUT = 15

# Event types
EVENT_SHELLY_CLOUD_CLICK = "shelly_cloud_click"
EVENT_SHELLY_CLOUD_ONLINE = "shelly_cloud_online"

# Event click types (Gen2 native)
CLICK_SINGLE = "single_push"
CLICK_DOUBLE = "double_push"
CLICK_TRIPLE = "triple_push"
CLICK_LONG = "long_push"

# Generation constants
GEN_1 = "G1"
GEN_2 = "G2"
GEN_BLE = "GBLE"

# Status keys (after Gen1->Gen2 normalisation)
KEY_SWITCH = "switch"
KEY_COVER = "cover"
KEY_LIGHT = "light"
KEY_INPUT = "input"
KEY_SYS = "sys"
KEY_WIFI = "wifi"
KEY_CLOUD = "cloud"
KEY_MQTT = "mqtt"
KEY_BLE = "ble"
KEY_DEVICE_POWER = "devicepower"
KEY_EM = "em"

# Manufacturer
MANUFACTURER = "Shelly"
