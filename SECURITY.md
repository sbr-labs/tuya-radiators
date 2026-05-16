# Security policy

## Reporting a vulnerability

Please report suspected security issues privately by opening a draft
security advisory on this repository:

> https://github.com/sbr-labs/tuya-radiators/security/advisories/new

Avoid filing public issues for security reports. We aim to acknowledge
every report within 7 days.

## Scope

This integration is a thin adapter over an existing Home Assistant Tuya
integration (`tuya` or `xtend_tuya`). It does not authenticate to Tuya
itself, does not store Tuya credentials, and does not open new outbound
endpoints. All cloud traffic flows through the host integration's
already-active session.

DPS values are logged at the debug log level for diagnostics. Tokens,
local keys and other credential material are never logged.

## Hardening

- Place your Tuya devices on a network VLAN that allows only the
  outbound endpoints the host integration needs (Tuya cloud + MQTT).
- Pin the host integration version that you have tested with this
  release. New host versions may change the API surface this
  integration borrows from.
- Treat any HA long-lived access token used to administer this
  integration with the same care as any HA admin credential.
