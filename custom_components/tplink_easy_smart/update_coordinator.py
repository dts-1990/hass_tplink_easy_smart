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
from .client.tplink_api import PoeState, PortPoeState, PortSpeed, PortState, TpLinkApi, PortBasedVLAN, IEEE1QVLAN
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
        self._port_based_vlan_enabled = False
        self._port_based_vlans: {int: [PortBasedVLAN]} = None
        self._1q_vlan_enabled = False
        self._1q_vlans: {int: [IEEE1QVLAN]} = None

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

    @property
    def get_port_based_vlan_enabled(self) -> bool:
        """Return port based vlan state of this device."""
        return self._port_based_vlan_enabled

    def get_port_based_vlan(self, number: int) -> int | None:
        """Return the switch PortBased VLAN."""
        if number > self.ports_count or number < 1:
            return None
        return self._port_states[number - 1].port_based_vlanid

    @property
    def get_1q_vlan_enabled(self) -> bool:
        """Return 802.1q vlan state of this device."""
        return self._1q_vlan_enabled

    def get_port_1q_pvid(self, number: int) -> int | None:
        """Return the port 802.1Q PVID."""
        if number > self.ports_count or number < 1:
            return None
        return self._port_states[number - 1].pvid_1q_vlanid

    def get_1q_vlans(self) ->  [int]:
        """Return the specified port state."""
        return self._1q_vlans.keys()

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
        await self._update_port_based_vlan_info()
        await self._update_1q_vlan_info()
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

    async def _update_port_based_vlan_info(self):
        """Update port PortBasedVLAN states."""
        try:
            result = await self._api.get_port_based_vlan_info()

            if not result[0] or not result[1]:
                self._port_based_vlan_enabled = False
                for port in self._port_states:
                    port.port_based_vlanid = None
                self._port_based_vlans = None
            else:
                self._port_based_vlan_enabled = True
                vlan_info = result[0]
                for port in self._port_states:
                    port.port_based_vlanid = vlan_info[port.number - 1]
                self._port_based_vlans = result[1]

            _LOGGER.debug("_update_port_based_vlan_info self._port_based_vlans=%s", str(self._port_based_vlans))
        except Exception as ex:
            _LOGGER.warning("Can not get port PortBasedVLAN: %s", repr(ex))
            for port in self._port_states:
                port.port_based_vlanid = None
            self._port_based_vlans = None

    async def _update_1q_vlan_info(self):
        """Update port IEEE1QVLAN states."""
        try:
            result = await self._api.get_1q_vlan_info()

            if not result[0] or not result[1]:
                self._1q_vlan_enabled = False
                for port in self._port_states:
                    port.pvid_1q_vlanid = None
                self._1q_vlans = None
            else:
                self._1q_vlan_enabled = True
                vlan_info = result[0]
                for port in self._port_states:
                    port.pvid_1q_vlanid = vlan_info[port.number - 1]
                self._1q_vlans = result[1]

        except Exception as ex:
            _LOGGER.warning("Can not get port IEEE1QVLAN: %s", repr(ex))
            for port in self._port_states:
                port.pvid_1q_vlanid = None
            self._1q_vlans = None

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

    async def async_set_port_based_vlan(self, port_id: int, vlan_name: str) ->  None:
        """Return the switch Port PortBasedVLAN."""
        # Check if after changed, old VLAN has no member, then delete it (except VLAN-1)
        del_action = False
        mod_old_action = False

        new_vlanid = int(vlan_name.removeprefix('VLAN-'))
        old_vlanid = self._port_states[port_id - 1].port_based_vlanid
        old_vlan = self._port_based_vlans.get(old_vlanid)
        if new_vlanid == 1 and old_vlanid != 1 and old_vlan != None and len(old_vlan.ports) == 1:  del_action = True
        elif new_vlanid == 1: mod_old_action = True

        new_vlan_ports: [int] = [port_id]
        if del_action:
            await self._api.del_port_based_vlan(
                old_vlanid
            )
        elif mod_old_action:
            old_vlan.ports.remove(port_id)
            new_vlan = self._port_based_vlans.get(new_vlanid)
            new_vlan_ports.extend(new_vlan.ports)
            await self._api.set_port_based_vlan(
                old_vlanid, old_vlan.ports
            )
        else:
            new_vlan = self._port_based_vlans.get(new_vlanid)
            if new_vlan is None: self._port_based_vlans[new_vlanid] = PortBasedVLAN(new_vlanid, new_vlan_ports)
            else: new_vlan_ports.extend(new_vlan.ports)
            await self._api.set_port_based_vlan(
                new_vlanid, new_vlan_ports
            )

        index = port_id - 1
        if len(self._port_states) >= index:
            self._port_states[index].port_based_vlanid = new_vlanid
            self._port_based_vlans[new_vlanid].ports = new_vlan_ports
            self.async_update_listeners()


    async def async_set_untag_1q_vlan(self, port_id: int, vlan_name: str) ->  None:
        """Set Port 802.11Q VLAN."""

        new_vlanid = int(vlan_name.removeprefix('VLAN-'))
        old_vlanid = self._port_states[port_id - 1].pvid_1q_vlanid
        index = port_id - 1
        if len(self._port_states) >= index:
            self._port_states[index].pvid_1q_vlanid = new_vlanid
            # Update old VLAN
            self._1q_vlans[old_vlanid].ungtag_ports.remove(port_id)
            self._1q_vlans[old_vlanid].notmem_ports.append(port_id)
            
            # Update new VLAN
            self._1q_vlans[new_vlanid].ungtag_ports.append(port_id)
            self._1q_vlans[new_vlanid].notmem_ports.remove(port_id)
            self.async_update_listeners()

         # Update new VLAN
        new_vlan = self._1q_vlans.get(new_vlanid)
        await self._api.set_1q_untag_vlan(
            new_vlanid, new_vlan.ungtag_ports, new_vlan.tag_ports, new_vlan.notmem_ports
        )

        # Update old VLAN
        old_vlan = self._1q_vlans.get(old_vlanid)
        await self._api.set_1q_untag_vlan(
            old_vlanid, old_vlan.ungtag_ports, old_vlan.tag_ports, old_vlan.notmem_ports
        )

        # Set new PVID
        await self._api.set_1q_port_pvid(
            port_id, new_vlanid
        )


