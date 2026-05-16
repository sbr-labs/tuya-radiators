"""Abstract device profile.

A profile describes the DPS mapping for a single radiator model.
Adding a new model = drop a new file in this package and register it
in __init__.PROFILES.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DpsField:
    """A single DPS with a human meaning, Tuya `code`, and value scaling.

    `dp` is the protocol-level index used by the LAN telemetry tap.
    `code` is the Tuya code (e.g. "switch", "temp_set") used by the
    sharing-cloud SDK for both status reads and command writes.
    """

    dp: int
    code: str = ""
    scale: float = 1.0

    def from_raw(self, raw: float | int | None) -> float | None:
        if raw is None:
            return None
        return float(raw) / self.scale

    def to_raw(self, value: float | int) -> int:
        return int(round(float(value) * self.scale))


@dataclass(frozen=True)
class PresetMap:
    """Bidirectional mapping between Tuya preset strings and HA preset names."""

    raw_to_preset: dict[str, str]

    def to_preset(self, raw: str | None) -> str | None:
        if raw is None:
            return None
        return self.raw_to_preset.get(raw)

    def to_raw(self, preset: str) -> str | None:
        for raw, name in self.raw_to_preset.items():
            if name == preset:
                return raw
        return None

    def presets(self) -> list[str]:
        return list(self.raw_to_preset.values())


@dataclass(frozen=True)
class ModelProfile:
    """Describes one radiator model."""

    key: str
    display_name: str
    manufacturer: str
    protocol: str
    min_temp_c: float
    max_temp_c: float
    target_step_c: float
    power: DpsField
    target_temp: DpsField
    current_temp: DpsField
    calibration: DpsField
    calibration_min: float
    calibration_max: float
    child_lock: DpsField
    preset: PresetMap | None
    preset_dps: DpsField | None = None
    window_detection_dps: DpsField | None = None
    window_detection_options: dict[str, str] = field(default_factory=dict)

    def all_fields(self) -> list[DpsField]:
        """Every DpsField referenced by this profile."""
        out: list[DpsField] = [
            self.power,
            self.target_temp,
            self.current_temp,
            self.calibration,
            self.child_lock,
        ]
        if self.preset_dps is not None:
            out.append(self.preset_dps)
        if self.window_detection_dps is not None:
            out.append(self.window_detection_dps)
        return out

    def dp_for_code(self, code: str) -> int | None:
        for f in self.all_fields():
            if f.code == code:
                return f.dp
        return None

    def code_for_dp(self, dp: int) -> str | None:
        for f in self.all_fields():
            if f.dp == dp:
                return f.code or None
        return None

    @property
    def product_ids(self) -> tuple[str, ...]:
        """Tuya product_ids this profile applies to."""
        return getattr(self, "_product_ids", ())
