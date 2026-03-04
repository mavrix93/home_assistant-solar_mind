"""Calendar platform for Solar Mind integration."""

import datetime
import logging
from typing import Any

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.solar_mind.ha.const import DOMAIN

from .ha.coordinator import SolarMindCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solar Mind calendar from a config entry."""
    coordinator: SolarMindCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SolarMindCalendar(coordinator, entry)])


class SolarMindCalendar(CoordinatorEntity[SolarMindCoordinator], CalendarEntity):
    """Representation of a Solar Mind calendar."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        CalendarEntityFeature.CREATE_EVENT
        | CalendarEntityFeature.DELETE_EVENT
        | CalendarEntityFeature.UPDATE_EVENT
    )

    def __init__(
        self,
        coordinator: SolarMindCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the calendar."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_calendar"
        self._attr_name = "Calendar"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, "Solar Mind"),
            manufacturer="Solar Mind",
            model="Energy Optimizer",
            entry_type=DeviceEntryType.SERVICE,
        )
        coordinator.calendar = self
        self._events: list[CalendarEvent] = [
            CalendarEvent(
                uid="1",
                summary="Discharging",
                start=datetime.datetime(2026, 2, 10, 0, 0, 0, tzinfo=datetime.timezone.utc),
                end=datetime.datetime(2026, 2, 10, 11, 10, 0, tzinfo=datetime.timezone.utc),
            ),
            CalendarEvent(
                uid="2",
                summary="Discharging",
                start=datetime.datetime(2026, 2, 11, 0, 0, 0, tzinfo=datetime.timezone.utc),
                end=datetime.datetime(2026, 2, 11, 11, 10, 0, tzinfo=datetime.timezone.utc),
            ),
            CalendarEvent(
                uid="3",
                summary="Charging",
                start=datetime.datetime(2026, 2, 11, 10, 0, 0, tzinfo=datetime.timezone.utc),
                end=datetime.datetime(2026, 2, 11, 12, 0, 0, tzinfo=datetime.timezone.utc),
            ),
        ]
        self._next_uid = 4

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        now = datetime.datetime.now(datetime.timezone.utc)
        upcoming = [e for e in self._events if e.end > now]
        if not upcoming:
            return None
        return min(upcoming, key=lambda e: e.start)

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        return [
            e for e in self._events
            if e.end > start_date and e.start < end_date
        ]

    def add_event(
        self,
        summary: str,
        start: datetime.datetime,
        end: datetime.datetime,
        description: str | None = None,
    ) -> None:
        """Add an event programmatically (called from coordinator)."""
        event = CalendarEvent(
            uid=str(self._next_uid),
            summary=summary,
            start=start,
            end=end,
            description=description,
        )
        self._next_uid += 1
        self._events.append(event)
        _LOGGER.debug("Recorded calendar event: %s", event)
        self.async_write_ha_state()

    async def async_create_event(self, **kwargs: Any) -> None:
        """Create a calendar event."""
        event = CalendarEvent(
            uid=str(self._next_uid),
            summary=kwargs.get("summary", "New Event"),
            start=kwargs["dtstart"],
            end=kwargs["dtend"],
            description=kwargs.get("description"),
            location=kwargs.get("location"),
        )
        self._next_uid += 1
        self._events.append(event)
        _LOGGER.debug("Created calendar event: %s", event)
        self.async_write_ha_state()

    async def async_delete_event(
        self,
        uid: str,
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Delete an event on the calendar."""
        self._events = [e for e in self._events if e.uid != uid]
        _LOGGER.debug("Deleted calendar event uid=%s", uid)
        self.async_write_ha_state()

    async def async_update_event(
        self,
        uid: str,
        event: dict[str, Any],
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Update an event on the calendar."""
        for i, existing in enumerate(self._events):
            if existing.uid == uid:
                self._events[i] = CalendarEvent(
                    uid=uid,
                    summary=event.get("summary", existing.summary),
                    start=event.get("dtstart", existing.start),
                    end=event.get("dtend", existing.end),
                    description=event.get("description", existing.description),
                    location=event.get("location", existing.location),
                )
                break
        _LOGGER.debug("Updated calendar event uid=%s", uid)
        self.async_write_ha_state()