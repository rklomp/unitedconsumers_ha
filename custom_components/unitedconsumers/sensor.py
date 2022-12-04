"""Platform for sensor integration."""
from __future__ import annotations

from datetime import timedelta
import logging

import async_timeout

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CURRENCY_EURO,
    ENERGY_KILO_WATT_HOUR,
    VOLUME_CUBIC_METERS,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN
from .pyuc import UcAuthError, UcError, UnitedConsumers

_LOGGER = logging.getLogger(__name__)

PRICE_EUR_KWH = f"EUR/{ENERGY_KILO_WATT_HOUR}"
PRICE_EUR_M3 = f"EUR/{VOLUME_CUBIC_METERS}"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""

    api = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = UcCoordinator(hass, api)

    add_entities(
        [
            UcTarifSensor(
                coordinator, "Low Tarif", "low", PRICE_EUR_KWH, config_entry.unique_id
            ),
            UcTarifSensor(
                coordinator, "High Tarif", "high", PRICE_EUR_KWH, config_entry.unique_id
            ),
            UcTarifSensor(
                coordinator,
                "Return Low Tarif",
                "ret-low",
                PRICE_EUR_KWH,
                config_entry.unique_id,
            ),
            UcTarifSensor(
                coordinator,
                "Return High Tarif",
                "ret-high",
                PRICE_EUR_KWH,
                config_entry.unique_id,
            ),
            UcTarifSensor(
                coordinator, "Gas Tarif", "gas", PRICE_EUR_M3, config_entry.unique_id
            ),
        ]
    )

    await coordinator.async_config_entry_first_refresh()


class UcCoordinator(DataUpdateCoordinator):
    """United Consumers custom coordinator."""

    _api: UnitedConsumers

    def __init__(self, hass, api):
        """Initialize UC coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="United Consumers Coordinator",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=3600),
        )
        self._api = api

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            async with async_timeout.timeout(10):
                return await self._api.fetch_data()
        except UcAuthError as err:
            # Raising ConfigEntryAuthFailed will cancel future updates
            # and start a config flow with SOURCE_REAUTH (async_step_reauth)
            raise ConfigEntryAuthFailed from err
        except UcError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err


class UcTarifSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Sensor."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, name, idx, unit, config_entry_unique_id):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        self._attr_name = f"United Consumers {name}"
        self._attr_native_unit_of_measurement = unit
        self._attr_unique_id = f"{config_entry_unique_id}_{idx}"
        self.idx = idx

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.coordinator.data.get(self.idx)
        super()._handle_coordinator_update()
