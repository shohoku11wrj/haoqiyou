"""Shared constants and enums used across the Haoqiyou utilities."""

from __future__ import annotations

from enum import Enum


class RouteOrientation(str, Enum):
    """Orientation labels for closed-loop routes."""

    CLOCKWISE = "clockwise"
    COUNTERCLOCKWISE = "counterclockwise"
