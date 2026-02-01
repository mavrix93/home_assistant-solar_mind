"""Tests for Solar Mind price adapter."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from custom_components.solar_mind.const import PriceSource
from custom_components.solar_mind.models import PriceData
from custom_components.solar_mind.price_adapter import PriceAdapter, create_price_adapter


def _make_state(state: str, attributes: dict | None = None) -> MagicMock:
    """Create a mock State-like object."""
    s = MagicMock()
    s.state = state
    s.attributes = attributes or {}
    return s


class TestPriceAdapterNordPool:
    """Test price adapter with Nord Pool format."""

    def test_parse_nord_pool_raw_today(self) -> None:
        """Nord Pool raw_today/raw_tomorrow are parsed."""
        hass = MagicMock()
        adapter = PriceAdapter(hass, PriceSource.NORD_POOL)
        today = datetime(2025, 2, 1, 0, 0, 0)
        state = _make_state(
            "0.05",
            {
                "raw_today": [
                    {"start": today.isoformat(), "value": 0.03},
                    {"start": (today.replace(hour=1)).isoformat(), "value": 0.04},
                ],
                "raw_tomorrow": [],
                "tomorrow_valid": False,
            },
        )
        result = adapter.parse_price_data(state)
        assert result.current_price == 0.05
        assert len(result.today) == 2
        assert result.today[0].price == 0.03
        assert result.today[1].price == 0.04
        assert result.tomorrow_available is False

    def test_parse_nord_pool_empty_state(self) -> None:
        """Nord Pool with empty attributes returns current price only."""
        hass = MagicMock()
        adapter = PriceAdapter(hass, PriceSource.NORD_POOL)
        state = _make_state("0.12", {})
        result = adapter.parse_price_data(state)
        assert result.current_price == 0.12
        assert len(result.today) == 0
        assert len(result.tomorrow) == 0


class TestPriceAdapterCzechOte:
    """Test price adapter with Czech OTE format."""

    def test_parse_czech_ote_current_price(self) -> None:
        """Czech OTE state is current price."""
        hass = MagicMock()
        adapter = PriceAdapter(hass, PriceSource.CZECH_OTE)
        state = _make_state("1.25", {"unit_of_measurement": "CZK/kWh"})
        result = adapter.parse_price_data(state)
        assert result.current_price == 1.25

    def test_parse_czech_ote_invalid_state(self) -> None:
        """Invalid state value sets current_price to None."""
        hass = MagicMock()
        adapter = PriceAdapter(hass, PriceSource.CZECH_OTE)
        state = _make_state("unknown", {})
        result = adapter.parse_price_data(state)
        assert result.current_price is None


class TestPriceAdapterGeneric:
    """Test price adapter generic/fallback."""

    def test_parse_generic_uses_state(self) -> None:
        """Generic uses state as current price."""
        hass = MagicMock()
        adapter = PriceAdapter(hass, PriceSource.GENERIC)
        state = _make_state("0.08", {})
        result = adapter.parse_price_data(state)
        assert result.current_price == 0.08


class TestCreatePriceAdapter:
    """Test factory function."""

    def test_create_with_string_source(self) -> None:
        """create_price_adapter accepts string source."""
        hass = MagicMock()
        adapter = create_price_adapter(hass, "nord_pool")
        assert adapter.source == PriceSource.NORD_POOL

    def test_create_with_enum_source(self) -> None:
        """create_price_adapter accepts PriceSource enum."""
        hass = MagicMock()
        adapter = create_price_adapter(hass, PriceSource.CZECH_OTE)
        assert adapter.source == PriceSource.CZECH_OTE
