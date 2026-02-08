"""Tests for Solar Mind price adapter."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from custom_components.solar_mind.const import PriceSource
from custom_components.solar_mind.ha.price_adapter import PriceAdapter, create_price_adapter


def _make_state(state: str, attributes: dict | None = None) -> MagicMock:
    """Create a mock State-like object."""
    s = MagicMock()
    s.state = state
    s.attributes = attributes or {}
    return s




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
