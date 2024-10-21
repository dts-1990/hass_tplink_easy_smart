"""Update coordinator for TP-Link."""
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client.classes import PoePowerLimit, PoePriority, TpLinkSystemInfo
from .client.const import FEATURE_POE
from .client.tplink_api import PoeState, PortPoeState, PortSpeed, PortState, TpLinkApi, PortVLAN, VLAN
from .const import ATTR_MANUFACTURER, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


# ---------------------------
#   TpLinkDataUpdateCoordinator
# ---------------------------
class TpLinkDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize."""
        self._config: ConfigEntry = config_entry

        self._api: TpLinkApi = TpLinkApi(
            host=config_entry.data[CONF_HOST],
            port=config_entry.data[CONF_PORT],
            use_ssl=config_entry.data[CONF_SSL],
            user=config_entry.data[CONF_USERNAME],
            password=config_entry.data[CONF_PASSWORD],
            verify_ssl=config_entry.data[CONF_VERIFY_SSL],
        )
        self._switch_info: TpLinkSystemInfo | None = None
        self._port_states: list[PortState] = []
        self._port_poe_states: list[PortPoeState] = []
        self._poe_state: PoeState | None = None
        self._ports_vlan: list[PortVLAN] = []
        self._vlans: {int: [VLAN]} = {}

        update_interval = config_entry.options.get(
            CONF_SCAN_INTERVAL,
            config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        super().__init__(
            hass,
            _LOGGER,
            name=config_entry.data[CONF_NAME],
            update_method=self.async_update,
            update_interval=timedelta(seconds=update_interval),
        )

    @property
    def unique_id(self) -> str:
        """Return the system descriptor."""
        entry = self.config_entry

        if entry.unique_id:
            return entry.unique_id

        return entry.entry_id

    @property
    def cfg_host(self) -> str:
        """Return the host of the device."""
        return self.config_entry.data[CONF_HOST]

    @property
    def ports_count(self) -> int:
        """Return ports count of the device."""
        return len(self._port_states)

    @property
    def ports_poe_count(self) -> int:
        """Return PoE ports count of the device."""
        return len(self._port_poe_states)

    def get_port_state(self, number: int) -> PortState | None:
        """Return the specified port state."""
        if number > self.ports_count or number < 1:
            return None
        return self._port_states[number - 1]

    def get_port_poe_state(self, number: int) -> PortPoeState | None:
        """Return the specified port PoE state."""
        if number > self.ports_poe_count or number < 1:
            return None
        return self._port_poe_states[number - 1]

    def get_switch_info(self) -> TpLinkSystemInfo | None:
        """Return the information of the switch."""
        return self._switch_info

    def get_poe_state(self) -> PoeState | None:
        """Return the switch PoE state."""
        return self._poe_state

    def get_port_vlan(self, number: int) -> PortVLAN | None:
        """Return the switch Port VLAN."""
        if number > self.ports_count or number < 1:
            return None
        return self._ports_vlan[number - 1]

    def _safe_disconnect(self, api: TpLinkApi) -> None:
        """Disconnect from API."""
        try:
            self.hass.async_add_job(api.disconnect)
        except Exception as ex:
            _LOGGER.warning("Can not schedule disconnect: %s", str(ex))

    async def is_feature_available(self, feature: str) -> bool:
        """Return true if specified feature is known and available."""
        return await self._api.is_feature_available(feature)

    async def async_update(self) -> None:
        """Asynchronous update of all data."""
        _LOGGER.debug("Update started")
        await self._update_switch_info()
        await self._update_port_states()
        await self._update_poe_state()
        await self._update_port_poe_states()
        await self._update_port_vlan_info()
        _LOGGER.debug("Update completed")

    def unload(self) -> None:
        """Unload the coordinator and disconnect from API."""
        self._safe_disconnect(self._api)

    async def _update_switch_info(self):
        """Update the switch info."""
        self._switch_info = await self._api.get_device_info()

    async def _update_port_states(self):
        """Update port states."""
        try:
            self._port_states = await self._api.get_port_states()
        except Exception as ex:
            _LOGGER.warning("Can not get port states: %s", repr(ex))
            self._port_states = []

    async def _update_poe_state(self):
        """Update the switch PoE state."""

        if not await self.is_feature_available(FEATURE_POE):
            return

        try:
            self._poe_state = await self._api.get_poe_state()
        except Exception as ex:
            _LOGGER.warning("Can not get poe state: %s", repr(ex))

    async def _update_port_poe_states(self):
        """Update port PoE states."""

        if not await self.is_feature_available(FEATURE_POE):
            return

        try:
            self._port_poe_states = await self._api.get_port_poe_states()
        except Exception as ex:
            _LOGGER.warning("Can not get port poe states: %s", repr(ex))
            self._port_poe_states = []

    async def _update_port_vlan_info(self):
        """Update port VLAN states."""
        try:
            result = await self._api.get_port_vlan_info()
            self._ports_vlan = result[0]
            self._vlans = result[1]
            _LOGGER.error("_update_port_vlan_info self._ports_vlan=%s", str(self._ports_vlan))
            _LOGGER.error("_update_port_vlan_info self._vlans=%s", str(self._vlans))
        except Exception as ex:
            _LOGGER.warning("Can not get port VLAN: %s", repr(ex))
            self._ports_vlan = []
            self._vlans = {}

    def get_device_info(self) -> DeviceInfo | None:
        """Return the DeviceInfo."""
        switch_info = self.get_switch_info()
        if not switch_info:
            _LOGGER.debug("Device info not found")
            return None

        result = DeviceInfo(
            configuration_url=self._api.device_url,
            identifiers={(DOMAIN, switch_info.mac)},
            manufacturer=ATTR_MANUFACTURER,
            name=switch_info.name,
            hw_version=switch_info.hardware,
            sw_version=switch_info.firmware,
        )
        return result

    async def set_port_state(
        self,
        number: int,
        enabled: bool,
        speed_config: PortSpeed,
        flow_control_config: bool,
    ) -> None:
        """Set the port state."""
        await self._api.set_port_state(
            number, enabled, speed_config, flow_control_config
        )

        index = number - 1
        if len(self._port_states) >= index:
            self._port_states[index].enabled = enabled
            self.async_update_listeners()

    async def async_set_poe_limit(self, limit: float) -> None:
        """Set general PoE limit."""
        await self._api.set_poe_limit(limit)
        await self._update_poe_state()
        self.async_update_listeners()

    async def async_set_port_poe_settings(
        self,
        port_number: int,
        enabled: bool,
        priority: PoePriority,
        power_limit: PoePowerLimit | float,
    ) -> None:
        """Set the port PoE settings."""
        await self._api.set_port_poe_settings(
            port_number, enabled, priority, power_limit
        )
        await self._update_port_poe_states()
        self.async_update_listeners()

    async def async_set_port_vlan(self, port_id: int, vlan_name: str) ->  None:
        """Return the switch Port VLAN."""
        # Check if after changed, old VLAN has no member, then delete it (except VLAN-1)
        del_action = False
        mod_old_action = False

        new_vlanid = int(vlan_name.removeprefix('VLAN-'))
        old_vlanid = self._ports_vlan[port_id - 1].vlanid
        old_vlan = self._vlans.get(old_vlanid)
        if new_vlanid == 1 and old_vlanid != 1 and old_vlan != None and len(old_vlan.ports) == 1:  del_action = True
        elif new_vlanid == 1: mod_old_action = True

        new_vlan_ports: [int] = [port_id]
        if del_action:
            await self._api.del_vlan(
                old_vlanid
            )
        elif mod_old_action:
            old_vlan.ports.remove(port_id)
            new_vlan = self._vlans.get(new_vlanid)
            new_vlan_ports.extend(new_vlan.ports)
            await self._api.set_vlan_ports(
                old_vlanid, old_vlan.ports
            )
        else:
            new_vlan = self._vlans.get(new_vlanid)
            if new_vlan is None: self._vlans[new_vlanid] = VLAN(new_vlanid, new_vlan_ports)
            else: new_vlan_ports.extend(new_vlan.ports)
            await self._api.set_vlan_ports(
                new_vlanid, new_vlan_ports
            )

        index = port_id - 1
        if len(self._ports_vlan) >= index:
            self._ports_vlan[index].vlanid = new_vlanid
            self._vlans[new_vlanid].ports = new_vlan_ports
            self.async_update_listeners()
