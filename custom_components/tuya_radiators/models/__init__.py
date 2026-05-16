"""Device model profiles."""

from __future__ import annotations

from .base import ModelProfile
from .ecostrad_iqceramic import ECOSTRAD_IQCERAMIC
from .ecostrad_iqceramic import PRODUCT_IDS as ECOSTRAD_IQCERAMIC_PIDS

PROFILES: dict[str, ModelProfile] = {
    ECOSTRAD_IQCERAMIC.key: ECOSTRAD_IQCERAMIC,
}

PRODUCT_ID_TO_PROFILE: dict[str, ModelProfile] = {
    pid: ECOSTRAD_IQCERAMIC for pid in ECOSTRAD_IQCERAMIC_PIDS
}


def get_profile(key: str) -> ModelProfile:
    return PROFILES[key]


def list_profiles() -> list[ModelProfile]:
    return list(PROFILES.values())


def profile_for_product(product_id: str) -> ModelProfile | None:
    return PRODUCT_ID_TO_PROFILE.get(product_id)
