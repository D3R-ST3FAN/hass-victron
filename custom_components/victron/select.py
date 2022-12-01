"""Support for Abode Security System switches."""
from __future__ import annotations

from typing import Any, cast

from enum import Enum

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription, DOMAIN as SELECT_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, HassJob
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import victronEnergyDeviceUpdateCoordinator
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import entity

from .const import DOMAIN, register_info_dict, SelectWriteType, CONF_ADVANCED_OPTIONS

from collections.abc import Callable
from homeassistant.helpers.typing import StateType

from datetime import timedelta
from homeassistant.util import utcnow
from homeassistant.helpers import event, entity

import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up victron select devices."""
    victron_coordinator: victronEnergyDeviceUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    _LOGGER.debug("attempting to setup select entities")
    descriptions = []
    #TODO cleanup
    if config_entry.options[CONF_ADVANCED_OPTIONS]:
        register_set = victron_coordinator.processed_data()["register_set"]
        for unit, registerLedger in register_set.items():
            for name in registerLedger:
                for register_name, registerInfo in register_info_dict[name].items():
                    if isinstance(registerInfo.entityType, SelectWriteType):
                        # _LOGGER.debug("unit == " + str(unit) + " registerLedger == " + str(registerLedger) + " registerInfo ")
                        # _LOGGER.debug("register_name")
                        # _LOGGER.debug(register_name)
                        descriptions.append(VictronEntityDescription(
                            key=register_name,
                            name=register_name.replace('_', ' '),
                            value_fn=lambda data: data["data"][register_name],
                            slave=unit,
                            register_ledger_key=name,
                            options=registerInfo.entityType.options,
                            address=registerInfo.register,
                        ))

    entities = []
    entity = {}
    for description in descriptions:
        entity = description
        entities.append(
            VictronSelect(
                hass,
                victron_coordinator,
                entity
                ))
    _LOGGER.debug("adding selects")
    _LOGGER.debug(entities)
    async_add_entities(entities)


@dataclass
class VictronEntityDescription(SelectEntityDescription):
    """Describes victron sensor entity."""
    options: Enum = None
    #TODO write unit references into this class and convert to base for all entity types
    #TODO cleanup unused
    slave: int = None
    address: int = None
    value_fn: Callable[[dict], StateType] = None#TODO cleanup
    register_ledger_key: str = None #TODO cleanup

class VictronSelect(CoordinatorEntity, SelectEntity):
    """Representation of an Victron switch."""

    def __init__(self, hass: HomeAssistant, coordinator: victronEnergyDeviceUpdateCoordinator, description: VictronEntityDescription) -> None:
        _LOGGER.debug("select init")
        self.coordinator = coordinator
        self.description: VictronEntityDescription = description
        #this needs to be changed to allow multiple of the same type
        self._attr_name = f"{description.name}"
        self.data_key = str(self.description.slave) + "." + str(self.description.key)

        self._attr_unique_id = f"{self.description.slave}_{self.description.key}"
        if self.description.slave not in (100, 225):
            self.entity_id = f"{SELECT_DOMAIN}.{DOMAIN}_{self.description.key}_{self.description.slave}"
        else:
            self.entity_id = f"{SELECT_DOMAIN}.{DOMAIN}_{self.description.key}"

        self._update_job = HassJob(self.async_schedule_update_ha_state)
        self._unsub_update = None
        super().__init__(coordinator)

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        _LOGGER.debug("select_async_update")
        try:
            #TODO see if entitydescription can be updated to include unit info and set it in init
            data = self.coordinator.processed_data()["data"][self.data_key]
            _LOGGER.debug("select data")
            _LOGGER.debug(data)
            self._attr_native_value = data
#TODO FURTHER DEBUG AND USE THIS FUNCTION IN DESCRIPTION INSTEAD
#            self._attr_native_value =  self.entity_description.value_fn(self.coordinator.processed_data())
        except (TypeError, IndexError):
            _LOGGER.debug("failed to retrieve value")
            # No data available
            self._attr_native_value = None

        # Cancel the currently scheduled event if there is any
        if self._unsub_update:
            self._unsub_update()
            self._unsub_update = None

        # Schedule the next update at exactly the next whole hour sharp
        self._unsub_update = event.async_track_point_in_utc_time(
            self.hass,
            self._update_job,
            utcnow() + timedelta(seconds=self.coordinator.interval),
        )


    @property
    def current_option(self) -> str:
        return  self.description.options(self.coordinator.processed_data()["data"][self.data_key]).name

    @property
    def options(self) -> list:
        return [option.name for option in self.description.options]

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        self.coordinator.write_register(unit=self.description.slave, address=self.description.address, value=self.coordinator.encode_scaling(int(self.description.options[option].value), "", 0))

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return the device info."""
        return entity.DeviceInfo(
            identifiers={
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, self.unique_id.split('_')[0])
            },
            name=self.unique_id.split('_')[1],
            model=self.unique_id.split('_')[0],
            manufacturer="victron", # TODO to be dynamically set for gavazzi and redflow
        )