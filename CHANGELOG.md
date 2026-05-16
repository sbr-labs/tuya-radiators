# Changelog

## 0.3.0-alpha (unreleased)

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
