# Tuya Radiators for Home Assistant

A focused Home Assistant integration for WiFi panel-heater radiators on
the Tuya / Smart Life platform (Ecostrad iQ Ceramic and same-platform
OEMs). It does the one thing the official `tuya` and `xtend_tuya`
integrations expose poorly: a clean climate entity per radiator, plus
power, child-lock, calibration, open-window-detection, surface-temp
sensor, and an on-demand refresh button — with fast UI response (~25 ms
optimistic flip) and explicit support for the Ecostrad firmware quirks.

## Design

These radiators (and their FLS-118C kin) ship with a firmware that
**silently drops local DPS writes** while still pushing telemetry over
the LAN. So a purely local integration cannot control them — every
setpoint, mode change or child-lock toggle has to go through the Tuya
cloud, no matter what the device's local key suggests.

Rather than re-implementing Tuya sign-in (which is fragile when more
than one HA integration shares a single account), this integration
**borrows the already-loaded `tuya_sharing.Manager` from your existing
`tuya` or `xtend_tuya` integration** at runtime. That means:

- Zero new sign-in. No QR codes, no user codes, no client IDs to paste.
- Tuya sees no extra terminal — your other Tuya integrations keep working.
- Token refresh, MQTT push and cloud auth are all handled by the host
  integration. We just wrap its API.

If neither `tuya` nor `xtend_tuya` is installed and signed in, this
integration won't have anything to borrow from — install one of those
first.

## What you get per radiator

| Entity | Purpose |
| --- | --- |
| `climate` | Target temperature (7–30 °C, 0.5 °C steps), current temperature, heat / off mode, presets: `comfort` / `eco` / `away` / `program` / `radiator` |
| `switch.power` | Direct power toggle (`mdi:radiator` / `mdi:radiator-off`) |
| `switch.child_lock` | Toggle the front-panel child lock |
| `number.calibration` | Adjust the radiator's internal temperature reading by ±5 °C |
| `select.window_detection` | Off / 60 min / 90 min open-window response |
| `sensor.surface_max_temp` | Read-only display of the surface-temperature cap used in `radiator` preset (30–70 °C). Firmware doesn't accept cloud writes to this value — set on the device's physical panel |
| `binary_sensor.online` | True when the device's WiFi is reachable from Tuya cloud |
| `button.refresh_from_cloud` | On-demand reconcile for one radiator (also available as the `tuya_radiators.refresh` service) |

### Presets

| Preset | Cloud `mode` | Heat source |
| --- | --- | --- |
| `program` | `auto` | Thermostat target (7–30 °C) following weekly schedule |
| `comfort` | `hot` | Thermostat target |
| `eco` | `eco` | Thermostat target |
| `away` | `cold` | Thermostat target |
| `radiator` | `only_inside` | Direct element/surface heating capped by `sensor.surface_max_temp` — thermostat target is ignored in this mode |

## Response time

UI control is **optimistic-first**: a toggle flips locally in under
150 ms while the cloud write completes in the background. A write-guard
prevents the periodic 30-second reconcile from clobbering a fresh write
before Tuya's cloud has propagated it.

## Supported hardware

| Brand / model | Tuya `product_id` | Status |
| --- | --- | --- |
| Ecostrad iQ Ceramic | `7vmieyhabmukishx` | Verified |
| Other FLS-118C OEM rebadges | various | Likely compatible — try the Ecostrad profile |

The profile system makes adding a new model a single file: drop a
`ModelProfile` into `custom_components/tuya_radiators/models/` and
register it in `models/__init__.py`. PRs welcome.

## Installation

### Prerequisite

Install **either** the official Home Assistant `tuya` integration **or**
the `xtend_tuya` HACS integration and sign it in to the Smart Life /
Tuya Smart account your radiators are paired with. Confirm your
radiators appear under that integration before continuing.

### Via HACS

1. HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/sbr-labs/tuya-radiators` as an Integration
3. Install "Tuya Radiators"
4. Restart Home Assistant
5. Settings → Devices & Services → Add Integration → Tuya Radiators

### Manual

Copy `custom_components/tuya_radiators/` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

A single-step config flow lists every radiator-class device visible to
the host integration. Tick the ones you want and submit. There is no
authentication step — the integration borrows the host's already-active
session.

To remove or add radiators later, delete the integration entry and add
it again.

## Privacy and security

- The integration stores no credentials of its own. Tuya tokens stay
  inside whichever host integration you borrow from.
- The integration logs DPS values at debug level for diagnostics; it
  never logs tokens or local keys.
- All outbound traffic flows through the host integration's existing
  Tuya cloud session. This integration adds no new outbound endpoints.
- See `SECURITY.md` for reporting policy.

## Licence

MIT — see `LICENSE`.
