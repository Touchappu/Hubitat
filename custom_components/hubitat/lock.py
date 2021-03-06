from logging import getLogger
from typing import Any, Dict, Optional, Union, cast

import hubitatmaker as hm
import voluptuous as vol

from homeassistant.components.lock import LockDevice
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_CODE,
    ATTR_CODE_LENGTH,
    ATTR_CODES,
    ATTR_LAST_CODE_NAME,
    ATTR_LENGTH,
    ATTR_MAX_CODES,
    ATTR_NAME,
    ATTR_POSITION,
    DOMAIN,
    SERVICE_CLEAR_CODE,
    SERVICE_SET_CODE,
    SERVICE_SET_CODE_LENGTH,
)
from .device import HubitatEntity
from .entities import create_and_add_entities
from .types import EntityAdder

_LOGGER = getLogger(__name__)


SET_CODE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_POSITION): vol.Coerce(int),
        vol.Required(ATTR_CODE): vol.Coerce(str),
        vol.Optional(ATTR_NAME): str,
    }
)
CLEAR_CODE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_ENTITY_ID): cv.entity_id, vol.Required(ATTR_POSITION): int}
)
SET_CODE_LENGTH_SCHEMA = vol.Schema(
    {vol.Required(ATTR_ENTITY_ID): cv.entity_id, vol.Required(ATTR_LENGTH): int}
)


class HubitatLock(HubitatEntity, LockDevice):
    """Representation of a Hubitat lock."""

    @property
    def code_format(self) -> Optional[str]:
        """Regex for code format or None if no code is required."""
        code_length = self.get_attr(hm.ATTR_CODE_LENGTH)
        if code_length is not None:
            return f"^\\d{code_length}$"
        return None

    @property
    def is_locked(self) -> bool:
        """Return True if the lock is locked."""
        return self.get_attr(hm.ATTR_LOCK) == hm.STATE_LOCKED

    @property
    def code_length(self) -> Optional[int]:
        return self.get_int_attr(hm.ATTR_CODE_LENGTH)

    @property
    def codes(self) -> Union[str, Dict[str, Dict[str, str]], None]:
        try:
            return self.get_json_attr(hm.ATTR_LOCK_CODES)
        except Exception:
            return self.get_str_attr(hm.ATTR_LOCK_CODES)

    @property
    def last_code_name(self) -> Optional[str]:
        return self.get_attr(hm.ATTR_LAST_CODE_NAME)

    @property
    def max_codes(self) -> Optional[int]:
        return self.get_int_attr(hm.ATTR_MAX_CODES)

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        return {
            ATTR_CODES: self.codes,
            ATTR_CODE_LENGTH: self.code_length,
            ATTR_LAST_CODE_NAME: self.last_code_name,
            ATTR_MAX_CODES: self.max_codes,
        }

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the lock."""
        await self.send_command(hm.CMD_LOCK)

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the lock."""
        await self.send_command(hm.CMD_UNLOCK)

    async def clear_code(self, position: int) -> None:
        await self.send_command(hm.CMD_DELETE_CODE, position)

    async def set_code(self, position: int, code: str, name: Optional[str]) -> None:
        arg = f"{position},{code}"
        if name is not None:
            arg = f"{arg},{name}"
        await self.send_command(hm.CMD_SET_CODE, arg)

    async def set_code_length(self, length: int) -> None:
        await self.send_command(hm.CMD_SET_CODE_LENGTH, length)


def is_lock(device: hm.Device) -> bool:
    """Return True if device looks like a fan."""
    return hm.CAP_LOCK in device.capabilities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: EntityAdder,
) -> None:
    """Initialize lock devices."""
    locks = await create_and_add_entities(
        hass, entry, async_add_entities, "lock", HubitatLock, is_lock
    )

    if len(locks) > 0:

        def get_entity(entity_id: str) -> Optional[HubitatLock]:
            for lock in locks:
                if lock.entity_id == entity_id:
                    return lock
            return None

        async def clear_code(service: ServiceCall):
            entity_id = cast(str, service.data.get(ATTR_ENTITY_ID))
            lock = get_entity(entity_id)
            if lock:
                pos = service.data.get(ATTR_POSITION)
                await lock.clear_code(pos)

        async def set_code(service: ServiceCall):
            entity_id = cast(str, service.data.get(ATTR_ENTITY_ID))
            lock = get_entity(entity_id)
            if not lock:
                raise ValueError(f"Invalid or unknown entity '{entity_id}'")

            pos = service.data.get(ATTR_POSITION)
            code = service.data.get(ATTR_CODE)
            name = service.data.get(ATTR_NAME)
            await lock.set_code(pos, code, name)
            _LOGGER.debug("Set code at %s to %s for %s", pos, code, entity_id)

        async def set_code_length(service: ServiceCall):
            entity_id = cast(str, service.data.get(ATTR_ENTITY_ID))
            lock = get_entity(entity_id)
            if lock:
                length = service.data.get(ATTR_LENGTH)
                await lock.set_code_length(length)
                _LOGGER.debug("Set code length for %s to %d", entity_id, length)

        hass.services.async_register(
            DOMAIN, SERVICE_CLEAR_CODE, clear_code, schema=CLEAR_CODE_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_SET_CODE, set_code, schema=SET_CODE_SCHEMA
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_CODE_LENGTH,
            set_code_length,
            schema=SET_CODE_LENGTH_SCHEMA,
        )
