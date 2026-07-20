# Shelly Cloud

Home Assistant custom integration that controls [Shelly](https://shelly.cloud) devices through the official Shelly Cloud API.

Designed for users who cannot (or do not want to) reach their Shelly devices on the local network and prefer the cloud-based control plane.

## Features

- Supports **Generation 1** and **Generation 2+** Shelly devices.
- Polls device state every 30 s through the v2 cloud endpoint (with v1 fallback for G1 devices).
- Maps each device to the most appropriate Home Assistant entity:
  - `switch`, `light`, `cover`, `sensor`, `binary_sensor`, `event`.
- Energy monitoring entities (power, energy, voltage, current) integrate with the Home Assistant Energy dashboard.
- Subentry-based device flow so you can add as many devices as you like to a single account.

## Installation

### HACS (recommended)

1. Open HACS → **Integrations** → ⋯ → **Custom repositories**.
2. Add `https://github.com/aNieto2k/hass-shelly-cloud` as **Integration**.
3. Download and restart Home Assistant.

### Manual

Copy `custom_components/shelly_cloud/` into your Home Assistant `config/custom_components/` directory and restart.

## Publishing a new release

To make a new version available through HACS, create a GitHub release whose tag matches the `version` field in `manifest.json`:

```bash
# After your changes
git add .
git commit -m "release: 0.2.0"
git tag 0.2.0                # tag must match manifest.json version
git push origin main
git push origin 0.2.0
```

Then in GitHub: **Releases → Draft a new release → choose tag `0.2.0`** → publish. HACS will pick up the new release automatically.

> The tag must **not** have a `v` prefix. The tag `0.2.0` is correct, `v0.2.0` will not be detected.

## Configuration

### 1. Get your credentials

In the Shelly Cloud app or at <https://control.shelly.cloud>:

1. Open **User settings → Authorization cloud key**.
2. Copy:
   - **Server URL** — your account's cloud host (e.g. `https://shelly-23.eu.shelly.cloud`).
   - **Authorization Cloud Key** — your personal auth key.

> The Authorization key has full access to your devices. Treat it like a password.

### 2. Add the integration

In Home Assistant: **Settings → Devices & services → Add integration → Shelly Cloud**.

You'll be asked for the **Server URL** and **Authorization Cloud Key**. Once the connection is validated, you'll immediately get a second modal to add your first device.

### 3. Add devices

For each Shelly device you want to control:

1. Open the Shelly Cloud app, navigate to **Device → Settings → Device Information → Device Id**.
2. Copy the hexadecimal **Device ID**.
3. In Home Assistant, on the Shelly Cloud integration card, click **+ Add device** and paste the ID.

The integration fetches the device metadata and creates the right entities for that model (relays → `switch`, covers → `cover`, RGBW bulbs → `light` with color support, etc.).

### Supported devices (examples)

| Model family | Generation | Entities |
|---|---|---|
| Shelly 1, 1PM, 2, 2.5, Plug, Plug S, H&T, Flood, Motion, Door/Window 2 | G1 | switch, sensor, binary_sensor, event |
| Shelly Plus 1, 1PM, 2PM, Plug S, Wall Dimmer, RGBW PM, Shelly Pro series | G2 | switch, light, cover, sensor, binary_sensor, event |

> BLU devices (battery-powered sensors) are not yet supported.

## Rate limits

The v2 cloud endpoint is limited to **1 request / second**. The integration batches up to 10 devices per request and uses an `AsyncLimiter` to respect that limit. Default poll interval is **30 seconds**, configurable through integration options.

## Diagnostics & troubleshooting

Enable debug logging:

```yaml
logger:
  default: warning
  logs:
    custom_components.shelly_cloud: debug
```

Download your device diagnostics from the device page to share with issue reports (auth keys are automatically redacted).

## License

MIT — see [LICENSE](LICENSE).
