"""Support for selects."""

from dataclasses import dataclass, field
import logging
from typing import Final

from homeassistant.components.select import (
    SelectEntity,
    SelectEntityDescription,
)

from .helpers import (
    generate_entity_id,
    generate_entity_name,
    generate_entity_unique_id,
    get_coordinator,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.entity_registry import async_get

from .update_coordinator import TpLinkDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

_FUNCTION_DISPLAYED_NAME_PORT_VLAN_SELECT_FORMAT: Final = "Port {} VLAN select"
_FUNCTION_UID_PORT_VLAN_SELECT_FORMAT: Final = "port_{}vlan_select"

ENTITY_DOMAIN: Final = "select"

# ---------------------------
#   TpLinkSelectEntityDescription
# ---------------------------
@dataclass
class TpLinkSelectEntityDescription(SelectEntityDescription):
    """A class that describes select entities."""

    function_name: str | None = None
    function_uid: str | None = None
    device_name: str | None = None
    name: str | None = field(init=False)

    def __post_init__(self):
        self.name = generate_entity_name(self.function_name, self.device_name)


# ---------------------------
#   async_setup_entry
# ---------------------------
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Netatmo energy platform schedule selector."""
    coordinator: TpLinkDataUpdateCoordinator = get_coordinator(hass, config_entry)

    selects = []
    _LOGGER.error("SONTD select ports_count=%s", coordinator.ports_count)

    for port_number in range(1, coordinator.ports_count + 1):
        selects.append(
            TpLinkPortVlanSelect(
                port_number,
                coordinator,
                TpLinkSelectEntityDescription(
                    key=f"port_{port_number}_vlan_select",
                    icon="mdi:lan",
                    device_name=coordinator.get_switch_info().name,
                    function_uid=_FUNCTION_UID_PORT_VLAN_SELECT_FORMAT.format(port_number),
                    function_name=_FUNCTION_DISPLAYED_NAME_PORT_VLAN_SELECT_FORMAT.format(
                        port_number
                    ),
                ),
            )
        )

    async_add_entities(selects)


# ---------------------------
#   TpLinkSelect
# ---------------------------
class TpLinkSelect(CoordinatorEntity[TpLinkDataUpdateCoordinator], SelectEntity):
    entity_description: TpLinkSelectEntityDescription

    def __init__(
        self,
        coordinator: TpLinkDataUpdateCoordinator,
        description: TpLinkSelectEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = coordinator.get_device_info()
        self._attr_unique_id = generate_entity_unique_id(
            coordinator, description.function_uid
        )
        self.entity_id = generate_entity_id(
            coordinator, ENTITY_DOMAIN, description.function_name
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._attr_available

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()
        _LOGGER.debug("%s added to hass", self.name)


# ---------------------------
#   TpLinkPortVlanSelect
# ---------------------------
class TpLinkPortVlanSelect(TpLinkSelect):
    """ Class for setting Port VLAN """
    _port_number: int | None = None
    def __init__(
        self,
        port_number: int,
        coordinator: TpLinkDataUpdateCoordinator,
        description: TpLinkSelectEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, description)
        self._port_number = port_number
        self._attr_extra_state_attributes = {}

    @property
    def options(self) -> list[str]:
        options = ['VLAN-' + str(i) for i in range(1, self.coordinator.ports_count + 1)]
        return options

    @property
    def current_option(self) -> str | None:
        vlanid = self.coordinator.get_port_vlan(self._port_number).vlanid
        _LOGGER.error("SONTD current_option  port=%s; vlan=%s", self._port_number, vlanid)
        return 'VLAN-' + str(vlanid)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._attr_available

    async def async_select_option(self,vlan_name: str) -> None:
        """Change the selected option."""
        await self.coordinator.async_set_port_vlan(
            self._port_number, vlan_name
        )
        #self.async_schedule_update_ha_state()

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()
        _LOGGER.debug("TpLinkPortVlanSelect[async_added_to_hass] %s added to hass", self.name)

    @callback
    def _handle_coordinator_update(self) -> None:
        port_vlan = self.coordinator.get_port_vlan(self._port_number)
        if port_vlan:
            _LOGGER.debug("TpLinkPortVlanSelect[_handle_coordinator_update] _port_number=%s,vlan=%s", self._port_number, port_vlan.vlanid)
            self._attr_available = True
            self._attr_extra_state_attributes["current_vlan"] = self.current_option
        else:
            _LOGGER.debug("TpLinkPortVlanSelect[_handle_coordinator_update] _port_number=%s  NO VLAN", self._port_number)
            self._attr_available = False

        super()._handle_coordinator_update()

