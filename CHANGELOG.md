# Changelog

## 0.5.1-alpha (unreleased)

Adds the radiator's second heating mode.

- New `number.{room}_radiator_surface_max_temp` per radiator
  (30-70 °C, 1 °C steps, writes DP 57 `cool_set_temp`). Caps the
  element/surface temperature used by the radiator's "Radiator" mode
  (cloud `mode = only_inside`) — the manual / non-thermostat heat
  source that goes well above the 30 °C thermostat ceiling.
- Renamed the climate preset `internal` → `radiator` to match the
  front-panel label on the Ecostrad iQ Ceramic.
- Profile now has `surface_max_temp` / `surface_min_temp_c` /
  `surface_max_temp_c` fields, all optional so non-iQ-Ceramic profiles
  can omit them.
- 3 new tests cover the new field's scaling, dp/code mapping, and
  preset rename. Suite at 36/36.

## 0.5.0-alpha

Reliability + failure-mode hardening.

- **Idempotent writes**: `async_set_dps(dp, v)` skips the cloud round-trip
  entirely if `v` is already the current state and no write is in flight.
- **One retry on cloud failure** with `WRITE_RETRY_DELAY_S` (default 2 s)
  backoff before revert. Catches transient blips that would previously
  cause a UI bounce.
- **Repair issue + persistent notification** after `FAILURE_THRESHOLD`
  consecutive failures on the same DP (default 3). Surfaces in HA's
  notification bell — not just in the log. Auto-clears on first success.
- **Stale-reconcile detection**: entities go `unavailable` if cloud
  hasn't responded in > `STALE_RECONCILE_S` (default 90 s). Truth in
  advertising — better than showing stale state as if it's live.
- **Reconcile-failure tracking**: account-level reconcile loop counts
  consecutive failures per device and raises a separate repair issue
  after 3 in a row. Auto-clears on first success.
- All thresholds exposed as constants in `const.py` for future tuning.
- 5 new tests covering idempotency, retry behaviour, failure-issue
  lifecycle, stale-cloud unavailability. Test suite at 34 / 34 passing.

## 0.4.0-alpha

Reliability and operator-control improvements.

- `binary_sensor.online` now reflects the cloud's per-device `online`
  flag (radiator WiFi state) instead of just "have we ever talked to
  cloud". A radiator that loses WiFi shows offline within ~30 s.
- New `button.{room}_radiator_refresh` per radiator — on-demand cloud
  reconcile for that one device. Useful after a brief cloud outage or
  when you've changed something in the Tuya app and don't want to
  wait for the next 30 s reconcile.
- New service `tuya_radiators.refresh` (optional `device_id`) for
  scripting/automation triggers of the same refresh.
- Coordinator now exposes a public `cloud` property so the new
  per-radiator surfaces can introspect the borrowed manager.

## 0.3.1-alpha

CI hardening.

- Real GitHub Action SHAs for `hacs/action` (was a fake hash) and
  `home-assistant/actions/hassfest`.
- `manifest.json` keys sorted as hassfest expects (`domain`, `name`,
  then alphabetical).
- Pytest now runs in CI alongside ruff / bandit / pip-audit.
- Filter for heating-class devices moved from `config_flow` into
  `list_radiator_devices` so the filter logic isn't duplicated.

## 0.3.0-alpha

Borrowed-manager rewrite. The integration no longer authenticates to
Tuya itself.

- Single-step config flow: pick radiators from a list. No user code,
  no QR, no client ID / secret.
- At runtime, borrows the already-loaded `tuya_sharing.Manager` from
  either the official `tuya` integration or `xtend_tuya`. Cloud
  writes, token refresh and MQTT push all stay with the host
  integration. Tuya sees no extra terminal.
- `after_dependencies: [tuya, xtend_tuya]` so setup waits for the host
  to finish loading on every HA restart — no more "auth gets forgotten"
  on update.
- Optimistic-first writes: UI flips in under 150 ms, cloud completes
  in the background. A 30-second write-guard prevents the reconcile
  loop from clobbering a fresh write before Tuya's cloud has propagated.
- Inline first-reconcile on startup so entities have state immediately
  rather than waiting for the 30-second loop.
- Dedicated `switch.power` entity per radiator alongside the existing
  climate `hvac_mode`, with state-aware `mdi:radiator` / `mdi:radiator-off`.
- Open-window-detection mapping fixed for the FLS-118C enum strings
  (`Off` / `Open_60min` / `Open_90min`); legacy integer values still
  recognised for compatibility.
- Mode preset map extended with `only_inside` → `internal` (the
  Ecostrad fifth preset that the cloud reports for this device class).
- Brand icons (`brand/icon.png` + `logo.png` and `@2x` variants) bundled
  for the 2026.3+ Brands Proxy API. Integration tile renders the icon
  without a brands-repo submission.

### Removed

- The standalone Tuya OpenAPI client (`cloud_api.py`) and the user-code
  sharing flow added in 0.2.0-alpha and 0.2.0-alpha2 are gone. Both
  proved unreliable when run alongside another Tuya integration on the
  same account (`-9999999 sign invalid` cascade).

## 0.2.0-alpha2 (deprecated)

Smart Life sharing flow with user-code + QR sign-in. Superseded by
0.3.0; see "Removed" above.

## 0.2.0-alpha (deprecated)

Tuya OpenAPI custom-project flow (client ID + secret). Superseded by
0.3.0; see "Removed" above.

## 0.1.0

Initial release. Local-only LAN protocol with persistent socket and
exponential-backoff reconnect. Worked for telemetry but could not
write to FLS-118C firmware (silent local-write drop discovered later);
removed in 0.3.0.
