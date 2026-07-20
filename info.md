# Shelly Cloud

## 0.1.0 — Initial release

First public version of the Shelly Cloud custom integration for Home Assistant.

### Features

- Connects to Shelly Cloud using the **Authorization Cloud Key** from `control.shelly.cloud`.
- Two-step setup: one config flow for the account, then subentry flows per device.
- Supports **Generation 1** and **Generation 2+** Shelly devices.
- Maps each device to the right Home Assistant entity automatically:
  - Relays (incl. lights wired to a relay) → `switch` / `light`
  - Dedicated lights → `light` with brightness, RGB, white, color temperature
  - Covers / rollers → `cover`
  - Sensors (power, energy, voltage, current, RSSI, uptime, RAM) → `sensor`
  - Inputs (switch mode), cloud / MQTT connectivity, online status → `binary_sensor`
- Polls the cloud v2 endpoint every 30 s in batches of up to 10 devices, respecting the 1 req/s rate limit.
- Re-fetches the legacy v1 endpoint for Gen 1 devices to expose `relay:0` / `roller:0` / `meter:0` data.
- Diagnostics support with the auth key automatically redacted.

### Known limitations

- Push events (button presses) are not supported because the integration uses polling only. WebSocket support is planned for 0.2.0.
- BLU devices (battery-powered sensors) are not yet supported.

See the [README](README.md) for installation and configuration.
