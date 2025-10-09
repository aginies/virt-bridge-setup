#!/usr/bin/env python3
# pylint: disable=too-many-lines,invalid-name
# SUSE LLC
# aginies@suse.com
"""
create a bridge on a slave interface
This was previously done by yast2 virtualization
Using NetworkManager API via dbus
"""

import argparse
import sys
import uuid
import logging
import socket
import struct
import readline
import cmd
from typing import Any, Dict, List, Optional
import dbus  # type: ignore

DBUS_SERVICE = 'org.freedesktop.NetworkManager'
DBUS_PATH = '/org/freedesktop/NetworkManager'
DBUS_SETTINGS_PATH = '/org/freedesktop/NetworkManager/Settings'
DBUS_NM_INTERFACE = 'org.freedesktop.NetworkManager'
DBUS_PROPERTIES_INTERFACE = 'org.freedesktop.DBus.Properties'
DBUS_SETTINGS_INTERFACE = 'org.freedesktop.NetworkManager.Settings'
DBUS_DEVICE_INTERFACE = 'org.freedesktop.NetworkManager.Device'
DBUS_IP4CONFIG_INTERFACE = 'org.freedesktop.NetworkManager.IP4Config'
DBUS_SETTINGS_CONNECTION_INTERFACE = 'org.freedesktop.NetworkManager.Settings.Connection'
DBUS_ACTIVE_CONNECTION_INTERFACE = 'org.freedesktop.NetworkManager.Connection.Active'

# Device types mapping
DEV_TYPES: Dict[int, str] = {
    0: "Unknown", 1: "Ethernet", 2: "Wi-Fi", 3: "WWAN", 4: "OLPC Mesh",
    5: "Bridge", 6: "Bluetooth", 7: "WiMAX", 8: "Modem", 9: "TUN",
    10: "InfiniBand", 11: "Bond", 12: "VLAN", 13: "ADSL", 14: "Team",
    15: "Generic", 16: "Veth", 17: "MACVLAN", 18: "OVS Port",
    19: "OVS Interface", 20: "Dummy", 21: "MACsec", 22: "IPVLAN",
    23: "OVS Bridge", 24: "IP Tunnel", 25: "Loopback", 26: "6LoWPAN",
    27: "HSR", 28: "Wi-Fi P2P", 29: "VRF", 30: "WireGuard",
    31: "WPAN", 32: "VRRP",
}

# Device states mapping
DEV_STATES: Dict[int, str] = {
    10: "Unmanaged", 20: "Unavailable", 30: "Disconnected", 40: "Prepare",
    50: "Config", 60: "Need Auth", 70: "IP Config", 80: "IP Check",
    90: "Secondaries", 100: "Activated", 110: "Deactivating", 120: "Failed",
}

DEFAULT_BRIDGE_CONN_NAME = 'c-mybr0'
DEFAULT_BRIDGE_IFNAME = 'mybr0'

class NMManager:
    """
    A class to manage NetworkManager via D-Bus.
    """

    def __init__(self) -> None:
        try:
            self.bus: dbus.SystemBus = dbus.SystemBus()
            self.nm_proxy: dbus.proxies = self.bus.get_object(
                DBUS_SERVICE,
                DBUS_PATH
            )
            self.nm_interface: dbus.proxies.Interface = dbus.Interface(
                self.nm_proxy,
                DBUS_NM_INTERFACE
            )
            self.nm_props_interface: dbus.proxies.Interface = dbus.Interface(
                self.nm_proxy,
                DBUS_PROPERTIES_INTERFACE
            )
            self.settings_proxy: dbus.proxies = self.bus.get_object(
                DBUS_SERVICE,
                DBUS_SETTINGS_PATH
            )
            self.settings_interface: dbus.proxies.Interface = dbus.Interface(
                self.settings_proxy,
                DBUS_SETTINGS_INTERFACE
            )
        except dbus.exceptions.DBusException as err:
            logging.error("Error connecting to D-Bus: %s", err)
            logging.error("Please ensure NetworkManager is running.")
            sys.exit(1)

    def _get_all_devices(self) -> List[Dict[str, Any]]:
        """
        Retrieves all devices and their properties from NetworkManager.
        """
        devices = []
        try:
            devices_paths = self.nm_interface.GetAllDevices()
            for dev_path in devices_paths:
                dev_proxy = self.bus.get_object(DBUS_SERVICE, dev_path)
                prop_interface = dbus.Interface(dev_proxy, DBUS_PROPERTIES_INTERFACE)
                all_props = prop_interface.GetAll(DBUS_DEVICE_INTERFACE)
                devices.append(all_props)
        except dbus.exceptions.DBusException as err:
            logging.error("Error getting devices: %s", err)
        return devices

    def select_default_slave_interface(self) -> Optional[str]:
        """
        Selects a default slave interface, prioritizing active devices with IP addresses.
        """
        interface_lists: Dict[str, List[str]] = {
            'eth_with_ip': [], 'eth_without_ip': [],
            'wifi_with_ip': [], 'wifi_without_ip': []
        }

        devices = self._get_all_devices()
        if not devices:
            logging.warning("No network devices found.")
            return None

        for device in devices:
            iface = device['Interface']
            dev_type = device['DeviceType']

            if iface == 'lo' or dev_type == 5 or any(
                    iface.startswith(p) for p in ['virbr', 'vnet', 'docker', 'p2p-dev-']):
                continue

            ip4_config_path = device['Ip4Config']
            has_ip = False
            if ip4_config_path != "/":
                ip4_config_proxy = self.bus.get_object(
                        DBUS_SERVICE, ip4_config_path)
                ip4_props_iface = dbus.Interface(
                        ip4_config_proxy, DBUS_PROPERTIES_INTERFACE)
                if ip4_props_iface.GetAll(
                        DBUS_IP4CONFIG_INTERFACE).get('Addresses'):
                    has_ip = True

            if dev_type == 1:  # Ethernet
                interface_lists['eth_with_ip' if has_ip else 'eth_without_ip'].append(iface)
            elif dev_type == 2:  # Wi-Fi
                interface_lists['wifi_with_ip' if has_ip else 'wifi_without_ip'].append(iface)

        for category in ['eth_with_ip', 'wifi_with_ip', 'eth_without_ip', 'wifi_without_ip']:
            if interface_lists[category]:
                selected_iface = sorted(interface_lists[category])[0]
                logging.info("Default slave interface selected: %s (%s)",
                             selected_iface, category.replace('_', ' ').title())
                return selected_iface

        logging.warning("No suitable default slave interface was found.")
        return None

    def get_slave_candidates(self) -> List[str]:
        """ Returns a list of all potential slave interfaces (Ethernet, Wi-Fi) """
        candidates: List[str] = []
        devices = self._get_all_devices()
        for device in devices:
            iface = device['Interface']
            dev_type = device['DeviceType']

            ignored_prefixes = ['lo', 'virbr', 'vnet', 'docker', 'p2p-dev-']
            if dev_type not in [1, 2] or dev_type == 5 or any(
                                iface.startswith(p) for p in ignored_prefixes
                                ):
                continue
            candidates.append(iface)
        candidates.sort()
        return candidates

    def _extract_bridge_settings(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Extracts bridge-specific settings from a connection configuration."""
        bridge_config = config.get('bridge', {})
        mac_bytes = bridge_config.get('mac-address')
        vlan_setting = bridge_config.get('vlan-filtering')
        return {
            'stp': 'Yes' if bridge_config.get('stp', True) else 'No',
            'priority': bridge_config.get('priority'),
            'forward-delay': bridge_config.get('forward-delay'),
            'multicast-snooping': 'Yes' if bridge_config.get('multicast-snooping', True) else 'No',
            'mac-address': ':'.join(f'{b:02X}' for b in mac_bytes) if mac_bytes else 'Not set',
            'vlan-filtering': 'Yes' if vlan_setting else 'No',
            'vlan-default-pvid': bridge_config.get('vlan-default-pvid')
        }

    def _extract_ipv4_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Extracts IPv4 configuration from a connection configuration."""
        ipv4_config = config.get('ipv4', {})
        return {
            'method': ipv4_config.get('method', 'disabled'),
            'addresses': [f"{addr[0]}/{addr[1]}" for addr in ipv4_config.get('addresses', [])],
            'gateway': ipv4_config.get('gateway', None),
            'dns': [str(d) for d in ipv4_config.get('dns', [])]
        }

    def find_existing_bridges(self) -> List[Dict[str, Any]]:
        """
        Finds all existing NetworkManager connections of type 'bridge'.
        """
        logging.debug("find_existing_bridges")
        all_connections_config = []
        connections_paths = self.settings_interface.ListConnections()
        for path in connections_paths:
            con_proxy = self.bus.get_object(DBUS_SERVICE, path)
            settings_connection = dbus.Interface(
                con_proxy,
                DBUS_SETTINGS_CONNECTION_INTERFACE
            )
            all_connections_config.append(settings_connection.GetSettings())

        slaves_by_master_uuid: Dict[str, List[Dict[str, str]]] = {}
        for config in all_connections_config:
            conn_settings = config.get('connection', {})
            if conn_settings.get('slave-type') == 'bridge' and conn_settings.get('master'):
                master_uuid = conn_settings.get('master')
                slave_details = {
                    'iface': conn_settings.get('interface-name', 'Unknown'),
                    'conn_id': conn_settings.get('id', 'Unknown Profile')
                }
                if master_uuid not in slaves_by_master_uuid:
                    slaves_by_master_uuid[master_uuid] = []
                slaves_by_master_uuid[master_uuid].append(slave_details)

        bridges = [
            {
                'id': config.get('connection', {}).get('id', 'N/A'),
                'uuid': config.get('connection', {}).get('uuid'),
                'interface-name': config.get('connection', {}).get('interface-name', 'N/A'),
                'slaves': slaves_by_master_uuid.get(config.get('connection', {}).get('uuid'), []),
                'ipv4': self._extract_ipv4_config(config),
                'bridge_settings': self._extract_bridge_settings(config),
            }
            for config in all_connections_config
            if config.get('connection', {}).get('type') == 'bridge'
        ]

        return bridges

    def show_existing_bridges(self, found_bridges: List[Dict[str, Any]]) -> None:
        """ Human readable form """
        logging.debug("show_existing_bridges %s", found_bridges)
        count = len(found_bridges)
        print(f"--- Found {count} Bridge(s) ---")
        for i, bridge in enumerate(found_bridges):
            print(f"  Bridge Profile: {bridge['id']}")
            print(f"  |- Interface:    {bridge['interface-name']}")
            print(f"  |- UUID:         {bridge['uuid']}")
            if bridge['slaves']:
                print("  |- Slave(s):")
                for slave in bridge['slaves']:
                    print(f"  |  |- {slave['iface']} (Profile: {slave['conn_id']})")
            else:
                print("  |- Slave:       (None)")
            b_settings = bridge['bridge_settings']
            print("  |- Bridge Settings:")
            print(f"  |  |- STP Enabled:   {b_settings['stp']}")
            print(f"  |  |- STP Priority:  {b_settings['priority']}")
            print(f"  |  |- Forward Delay: {b_settings['forward-delay']}")
            print(f"  |  |- IGMP snooping: {b_settings['multicast-snooping']}")
            print(f"  |  |- VLAN Filtering: {b_settings['vlan-filtering']}")
            if b_settings['vlan-filtering'] == "Yes":
                print(f"  |  |- vlan-default-pvid:    {b_settings['vlan-default-pvid']}")
            print(f"  |  |- MAC:    {b_settings['mac-address']}")
            ipv4 = bridge['ipv4']
            live_config = self._get_active_network_config(bridge['interface-name'])
            if live_config:
                ipv4.update(live_config)
            print(f"  |- IPv4 Config:  ({ipv4['method']})")
            print(f"  |  |- Address: {', '.join(ipv4['addresses']) or '(Not set)'}")
            print(f"  |  |- Gateway: {ipv4['gateway'] or '(Not set)'}")
            print(f"  |   - DNS:     {', '.join(ipv4['dns']) or '(Not set)'}")
            if i < count - 1:
                print("")

    # pylint: disable=too-many-locals
    def _create_bridge_settings(self, config: Dict[str, Any], bridge_uuid: str) -> Dict[str, Any]:
        """
        Creates the bridge settings dictionary.
        """
        bridge_conn_name = config['conn_name']
        bridge_ifname = config['bridge_ifname']
        slave_iface = config['slave_interface']
        stp = config.get('stp', 'yes')
        stp_priority = config.get('stp_priority', None)
        clone_mac = config.get('clone_mac', True)
        forward_delay = config.get('forward_delay', None)
        multicast_snooping = config.get('multicast_snooping', 'yes')
        vlan_filtering = config.get('vlan_filtering', 'no')
        vlan_default_pvid = config.get('vlan_default_pvid', None)

        bridge_settings = {
            'connection': {
                'id': dbus.String(bridge_conn_name),
                'uuid': dbus.String(bridge_uuid),
                'type': dbus.String('bridge'),
                'interface-name': dbus.String(bridge_ifname),
            },
            'bridge': {},
            'ipv4': {'method': dbus.String('auto')},
            'ipv6': {'method': dbus.String('auto')},
        }

        if stp:
            bridge_settings['bridge']['stp'] = dbus.Boolean(stp.lower() == 'yes')

        if stp_priority is not None:
            if not 0 <= stp_priority <= 65535:
                logging.error("Error: STP priority must be between 0 and 65535.")
                sys.exit(1)
            bridge_settings['bridge']['priority'] = dbus.UInt16(stp_priority)

        if multicast_snooping:
            bridge_settings['bridge']['multicast-snooping'] = dbus.Boolean(
                                                    multicast_snooping.lower() == 'yes'
                                                    )

        if clone_mac:
            mac_address = self._get_mac_address(slave_iface)
            logging.info("MAC address of %s is %s", slave_iface, mac_address)
            if mac_address:
                mac_bytes = [int(x, 16) for x in mac_address.split(':')]
                bridge_settings['bridge']['mac-address'] = dbus.ByteArray(mac_bytes)

        if forward_delay is not None:
            if not 0 <= forward_delay <= 30:
                logging.error("Error: Forward delay must be between 0 and 30.")
                sys.exit(1)
            bridge_settings['bridge']['forward-delay'] = dbus.UInt16(forward_delay)

        if vlan_filtering:
            bridge_settings['bridge']['vlan-filtering'] = dbus.Boolean(
                                                    vlan_filtering.lower() == 'yes'
                                                    )
        if vlan_default_pvid is not None:
            if not 0 <= vlan_default_pvid <= 4094:
                logging.error("Error: Port VLAN id must be between 0 and 4094.")
                sys.exit(1)
            bridge_settings['bridge']['vlan-default-pvid'] = dbus.UInt16(vlan_default_pvid)

        return bridge_settings

    def add_bridge_connection(self, config: Dict[str, Any]) -> None:
        """ Creates a bridge and enslaves a physical interface to it """
        logging.debug("add_bridge_connection %s", config)
        bridge_conn_name = config['conn_name']
        slave_iface = config['slave_interface']
        dry_run = config.get('dry_run', False)

        if not self.check_interface_exist(slave_iface):
            logging.error("Slave interface %s does not exist", slave_iface)
            return

        slave_conn_name = f"{bridge_conn_name}-port-{slave_iface}"
        self.delete_connection(bridge_conn_name, False, dry_run)
        self.delete_connection(slave_conn_name, False, dry_run)

        bridge_uuid = str(uuid.uuid4())
        bridge_settings = self._create_bridge_settings(config, bridge_uuid)

        logging.debug("Bridge settings %s", bridge_settings)

        try:
            if not dry_run:
                logging.info("Creating bridge profile %s...", bridge_conn_name)
                bridge_path = self.settings_interface.AddConnection(bridge_settings)
                logging.info("Successfully added bridge profile. Path: %s", bridge_path)
            else:
                logging.info("DRY-RUN: Successfully added bridge profile")
        except dbus.exceptions.DBusException as err:
            logging.error("Error adding bridge connection profile: %s", err)
            return

        slave_settings = {
            'connection': {
                'id': dbus.String(slave_conn_name),
                'uuid': dbus.String(str(uuid.uuid4())),
                'type': dbus.String('802-3-ethernet'),
                'interface-name': dbus.String(slave_iface),
                'master': dbus.String(bridge_uuid),
                'slave-type': dbus.String('bridge'),
            },
        }
        logging.debug("Slave settings: %s", slave_settings)

        try:
            logging.info("Creating slave profile %s for interface %s...",
                        slave_conn_name, slave_iface
                        )
            if not dry_run:
                self.settings_interface.AddConnection(slave_settings)
                logging.info("Successfully enslaved interface %s to bridge.",
                             slave_iface)
            else:
                logging.info("DRY-RUN: Successfully enslaved interface %s to bridge.",
                             slave_iface)
        except dbus.exceptions.DBusException as err:
            logging.error("Error adding slave connection profile: %s", err)
            logging.error("Cleaning up bridge profile due to error...")
            self.delete_connection(bridge_conn_name, False, dry_run)
            self.delete_connection(slave_conn_name, False, dry_run)

    def _get_active_network_config(self, interface_name: str) -> Optional[Dict[str, Any]]:
        """
        For a given interface name, finds the active device and returns its live network config.
        """
        logging.debug("_get_active_network_config %s", interface_name)
        if not interface_name:
            return None
        try:
            dev_path = self.nm_interface.GetDeviceByIpIface(interface_name)
            dev_proxy = self.bus.get_object(DBUS_SERVICE, dev_path)
            prop_interface = dbus.Interface(dev_proxy, DBUS_PROPERTIES_INTERFACE)
            all_props = prop_interface.GetAll(DBUS_DEVICE_INTERFACE)
            ip4_config_path = all_props['Ip4Config']
            if ip4_config_path == "/":
                return None

            ip4_config_proxy = self.bus.get_object(
                                        DBUS_SERVICE,
                                        ip4_config_path
                                        )
            ip4_props_iface = dbus.Interface(ip4_config_proxy, DBUS_PROPERTIES_INTERFACE)
            ip4_props = ip4_props_iface.GetAll(DBUS_IP4CONFIG_INTERFACE)

            addresses = [
                f"{socket.inet_ntoa(struct.pack('<L', int(addr_data[0])))}/{addr_data[1]}"
                for addr_data in ip4_props.get('Addresses', [])
            ]
            dns = [
                socket.inet_ntoa(struct.pack('<L', int(d)))
                for d in ip4_props.get('Nameservers', [])
            ]
            gateway = ip4_props.get('Gateway', 0)

            return {
                'addresses': addresses,
                'gateway': gateway,
                'dns': dns
            }
        except dbus.exceptions.DBusException:
            return None

    def _get_mac_address(self, iface_name: str) -> Optional[str]:
        """ Helper to get the MAC address for a given interface name """
        logging.debug("_get_mac_address %s", iface_name)
        devices = self._get_all_devices()
        for device in devices:
            if device['Interface'] == iface_name:
                mac = device.get('HwAddress')
                if mac:
                    logging.info("Found MAC address for %s: %s", iface_name, mac)
                    return mac
        logging.warning("Warning: Could not find MAC address for interface %s.", iface_name)
        return None

    def find_connection(self, name_or_uuid: str) -> Optional[str]:
        """ Finds a connection by its name (ID) or UUID """
        logging.debug("find_connection %s", name_or_uuid)
        connections = self.settings_interface.ListConnections()
        for path in connections:
            con_proxy = self.bus.get_object(DBUS_SERVICE, path)
            settings_connection = dbus.Interface(
                                        con_proxy,
                                        DBUS_SETTINGS_CONNECTION_INTERFACE
                                        )
            config = settings_connection.GetSettings()
            if name_or_uuid in (config['connection']['id'], config['connection']['uuid']):
                logging.info("Found connection %s", config['connection']['id'])
                logging.info("  UUID: %s", config['connection']['uuid'])
                logging.info("  Path: %s", path)
                return path
        return None

    def delete_connection(self, name_or_uuid: str, show_list: bool, dry_run: bool = False) -> None:
        """ Deletes a connection """
        logging.debug("delete_connection %s %s", name_or_uuid, show_list)
        path = self.find_connection(name_or_uuid)
        if path:
            if dry_run:
                logging.info("DRY-RUN: Would delete connection %s.", name_or_uuid)
                return
            try:
                con_proxy = self.bus.get_object(DBUS_SERVICE, path)
                connection = dbus.Interface(
                    con_proxy,
                    DBUS_SETTINGS_CONNECTION_INTERFACE
                )
                connection.Delete()
                logging.info("Successfully deleted connection %s.", name_or_uuid)
            except dbus.exceptions.DBusException as err:
                logging.error("Error deleting connection: %s", err)
        else:
            logging.info("Connection %s not found to delete.", name_or_uuid)
            if show_list is True:
                logging.info("Connection available are:")
                self.list_connections()

    def activate_connection(self, name_or_uuid: str, dry_run: bool = False) -> None:
        """ Activates a connection """
        logging.debug("activate_connection %s", name_or_uuid)
        conn_path = self.find_connection(name_or_uuid)
        if not conn_path:
            logging.info("Connection %s not found to activate.", name_or_uuid)
            logging.info("Connection available are:")
            self.list_connections()
            return

        try:
            if dry_run :
                logging.info("DRY-RUN: Activating %s...", name_or_uuid)
            else:
                logging.info("Activating %s...", name_or_uuid)
                self.nm_interface.ActivateConnection(conn_path, "/", "/")
            logging.info("Activation command sent for %s. Check status manually.", name_or_uuid)
        except dbus.exceptions.DBusException as err:
            logging.error("Error activating connection: %s", err)
            raise

    def deactivate_connection(self, name_or_uuid: str, dry_run: bool = False) -> None:
        """ Deactivates a connection """
        logging.debug("deactivate_connection %s", name_or_uuid)
        active_connections = self.nm_props_interface.Get(
            DBUS_NM_INTERFACE,
            'ActiveConnections'
        )
        active_conn_path_to_deactivate = None

        for path in active_connections:
            ac_proxy = self.bus.get_object(DBUS_SERVICE, path)
            prop_interface = dbus.Interface(ac_proxy, DBUS_PROPERTIES_INTERFACE)

            conn_settings_path = prop_interface.Get(
                                            DBUS_ACTIVE_CONNECTION_INTERFACE,
                                            'Connection'
                                            )

            settings_proxy = self.bus.get_object(
                                    DBUS_SERVICE,
                                    conn_settings_path
                                    )
            settings_iface = dbus.Interface(
                                    settings_proxy,
                                    DBUS_SETTINGS_CONNECTION_INTERFACE
                                    )
            settings = settings_iface.GetSettings()
            conn_id = settings['connection']['id']

            if conn_id == name_or_uuid:
                active_conn_path_to_deactivate = path
                break

        if active_conn_path_to_deactivate:
            try:
                if dry_run:
                    logging.info("DRY_RUN: Deactivating %s ...", name_or_uuid)
                else:
                    logging.info("Deactivating %s ...", name_or_uuid)
                    self.nm_interface.DeactivateConnection(active_conn_path_to_deactivate)
                logging.info("Successfully deactivated %s.", name_or_uuid)
            except dbus.exceptions.DBusException as err:
                logging.error("Error deactivating connection: %s", err)
        else:
            print(f"Connection '{name_or_uuid}' is not active or could not be found.")
            logging.info("Connection available are:")
            self.list_connections()

    def _get_connections(self) -> List[Dict[str, Any]]:
        """Retrieves details for all saved NetworkManager connections without printing."""
        logging.debug("_get_connections")
        all_connections = []
        connections_paths = self.settings_interface.ListConnections()
        for path in connections_paths:
            con_proxy = self.bus.get_object(DBUS_SERVICE, path)
            settings_iface = dbus.Interface(
                con_proxy,
                DBUS_SETTINGS_CONNECTION_INTERFACE
            )
            config = settings_iface.GetSettings()

            connection_settings = config.get('connection', {})
            conn_details = {
                'id': connection_settings.get('id', 'N/A'),
                'uuid': connection_settings.get('uuid', 'N/A'),
                'type': connection_settings.get('type', 'N/A'),
                'interface-name': connection_settings.get('interface-name', '---')
            }
            all_connections.append(conn_details)
        return all_connections

    def list_connections(self) -> None:
        """
        Retrieves and prints details for all saved NetworkManager connections
        """
        logging.debug("list_connections")
        all_connections = self._get_connections()
        print(f"{ 'NAME (ID)':<30} { 'TYPE':<18} { 'INTERFACE':<15} { 'UUID'}")
        print("=" * 105)
        for conn in sorted(all_connections, key=lambda c: c['id']):
            print(f"{conn['id']:<30} "
                  f"{conn['type']:<18} "
                  f"{conn['interface-name']:<15} "
                  f"{conn['uuid']}"
                  )

    def check_interface_exist(self, interface: str) -> bool:
        """Check if an interface exists."""
        logging.debug("check_interface_exist %s", interface)
        devices = self._get_all_devices()
        for device in devices:
            if device['Interface'] == interface:
                return True
        return False

    def get_all_connection_identifiers(self) -> List[str]:
        """Returns a flat list of all connection IDs and UUIDs for completion."""
        identifiers: List[str] = []
        connections = self._get_connections()
        for conn in connections:
            identifiers.append(conn['id'])
            identifiers.append(conn['uuid'])
        return identifiers

    def list_devices(self) -> None:
        """
        Lists all available network devices and their properties in a table
        """
        logging.debug("list_devices")
        logging.info("Querying for available devices...")
        devices = self._get_all_devices()
        if not devices:
            logging.error("No network devices found.")
            return

        print(
            f"{ 'INTERFACE':<15} "
            f"{ 'DEV TYPE':<12} "
            f"{ 'MAC ADDRESS':<20} "
            f"{ 'STATE':<15} "
            f"{ 'CONNECTION':<18} "
            f"{ 'AUTOCONNECT':<10}"
            )
        print("=" * 105)

        for device in devices:
            iface = device['Interface']
            dev_type_num = device['DeviceType']
            # WORKAROUND: Corrects known DeviceType bugs from certain NetworkManager versions.
            if dev_type_num == 13 and ('br' in iface or 'virbr' in iface):
                dev_type_num = 5
            elif dev_type_num == 30 and iface.startswith('p2p-dev-'):
                dev_type_num = 28

            active_conn_path = device['ActiveConnection']
            conn_name = "---"
            if active_conn_path != "/":
                ac_proxy = self.bus.get_object(
                                            DBUS_SERVICE,
                                            active_conn_path
                                            )
                ac_props_iface = dbus.Interface(
                                            ac_proxy,
                                            DBUS_PROPERTIES_INTERFACE
                                            )
                conn_settings_path = ac_props_iface.Get(
                                        DBUS_ACTIVE_CONNECTION_INTERFACE,
                                        'Connection'
                                        )

                settings_proxy = self.bus.get_object(
                                                DBUS_SERVICE,
                                                conn_settings_path
                                                )
                settings_iface = dbus.Interface(
                                        settings_proxy,
                                        DBUS_SETTINGS_CONNECTION_INTERFACE
                                        )
                settings = settings_iface.GetSettings()
                conn_name = settings['connection']['id']

            print(
                f"{iface:<15} "
                f"{DEV_TYPES.get(dev_type_num, f'Unknown ({dev_type_num})'):<12} "
                f"{device.get('HwAddress', '---'):<20} "
                f"{DEV_STATES.get(device['State'], f'Unknown ({device['State']})'):<15} "
                f"{conn_name:<18} "
                f"{('Yes' if device['Autoconnect'] else 'No'):<12}"
                )

class CommandHandler:
    """
    Handles command-line arguments and dispatches commands to the NMManager class.
    """

    def __init__(self, manager: NMManager):
        self.manager = manager

    def execute(self, args: argparse.Namespace) -> None:
        """
        Executes the command specified in the command-line arguments.
        """
        if args.command == 'add':
            self.handle_add_bridge(args)
        elif args.command == 'interactive':
            self.handle_interactive()
        elif args.command == 'dev':
            self.manager.list_devices()
        elif args.command == 'conn':
            self.manager.list_connections()
        elif args.command == 'delete':
            self.manager.delete_connection(args.name, True, args.dry_run)
        elif args.command == 'activate':
            self.manager.activate_connection(args.name, args.dry_run)
        elif args.command == 'deactivate':
            self.manager.deactivate_connection(args.name, args.dry_run)
        elif args.command == 'showb':
            found_bridges = self.manager.find_existing_bridges()
            if not found_bridges:
                logging.info("No existing bridge connections found.")
            else:
                self.manager.show_existing_bridges(found_bridges)

    def handle_add_bridge(self, args: argparse.Namespace) -> None:
        """
        Handles the 'add' command.
        """
        found_bridges = self.manager.find_existing_bridges()
        if found_bridges and not getattr(args, 'force', False):
            logging.info(
                "There is already some bridges on this system\n"
                "use --force option to create another one"
            )
            self.manager.show_existing_bridges(found_bridges)
            sys.exit(1)

        slave_interface = getattr(args, 'slave_interface', None)
        if not slave_interface:
            slave_interface = self.manager.select_default_slave_interface()
            args.slave_interface = slave_interface

        if not slave_interface:
            logging.error("No slave interface specified and no default found.")
            sys.exit(1)

        if not self.manager.check_interface_exist(slave_interface):
            logging.error("No interface: %s", slave_interface)
            self.manager.list_devices()
            sys.exit(1)

        self.manager.add_bridge_connection(vars(args))
        slave_conn_name = f"{args.conn_name}-port-{slave_interface}"
        if not getattr(args, 'dry_run', False):
            try:
                self.manager.activate_connection(slave_conn_name)
            except dbus.exceptions.DBusException:
                logging.error(
                    "Failed to activate the slave connection."
                    " The connection profile that was just created will be removed"
                )
                self.manager.delete_connection(args.conn_name, False)
                self.manager.delete_connection(slave_conn_name, False)
                sys.exit(1)

    def handle_interactive_add(self, arg_string: str) -> None:
        """
        Handles the 'add' command from the interactive shell.
        """
        parser = argparse.ArgumentParser(prog='add', description='Add a new bridge connection.')
        parser.add_argument('--conn-name', dest='conn_name', help=help_data['help_conn_name'],
                            default=DEFAULT_BRIDGE_CONN_NAME)
        parser.add_argument('--bridge-ifname', dest='bridge_ifname',
                            help=help_data['help_bridge_ifname'],
                            default=DEFAULT_BRIDGE_IFNAME)
        parser.add_argument('--slave-interface', dest='slave_interface',
                            help=help_data['help_slave_interface'])
        parser.add_argument('--no-clone-mac', dest='clone_mac', action='store_false',
                            default=True, help=help_data['clone_mac'],)
        parser.add_argument('--stp', choices=['yes', 'no'], default='yes', help=help_data['stp'])
        parser.add_argument('--fdelay', type=int, dest='forward_delay', help=help_data['fdelay'])
        parser.add_argument('--stp-priority', type=int, dest='stp_priority',
                            help=help_data['stp_priority'])
        parser.add_argument('--multicast-snooping', choices=['yes', 'no'],
                            default='yes', dest='multicast_snooping',
                            help=help_data['multicast_snooping'])
        parser.add_argument('--vlan-filtering', choices=['yes', 'no'],
                            default='no', dest='vlan_filtering', help=help_data['vlan_filtering'])
        parser.add_argument('--vlan-default-pvid', type=int, default=None,
                    dest='vlan_default_pvid', help=help_data['vlan_default_pvid'])
        try:
            args = parser.parse_args(arg_string.split())
            args.force = True # In interactive mode, we always force add
            args.dry_run = False
            self.handle_add_bridge(args)
        except SystemExit:
            pass

    def handle_interactive(self) -> None:
        """
        Handles the 'interactive' command.
        """
        InteractiveShell(self.manager, self).cmdloop()
        sys.exit(0)

class InteractiveShell(cmd.Cmd):
    """ A simple interactive shell to manage NetworkManager bridges """
    intro = "\nWelcome to the interactive virt-bridge-setup shell.\n"
    intro += "Type `help` or `?` to list commands.\n"
    promptline = '''_________________________________________
'''
    prompt = promptline + "virt-bridge #> "

    def __init__(self, manager: 'NMManager', handler: 'CommandHandler') -> None:
        super().__init__()
        self.manager = manager
        self.handler = handler
        try:
            delims = readline.get_completer_delims()
            delims = delims.replace('-', '')
            readline.set_completer_delims(delims)
        except ImportError:
            pass

    def do_add(self, arg_string: str) -> None:
        """
        Adds a new bridge connection with specified options
        """
        logging.debug("do_add %s", arg_string)
        self.handler.handle_interactive_add(arg_string)

    def complete_add(self, text: str, line: str, begidx: int, _endidx: int) -> List[str]:
        """ Provides context-aware auto-completion for the 'add' command """
        words_before_cursor = line[:begidx].split()
        if not words_before_cursor:
            return []
        last_full_word = words_before_cursor[-1]
        if last_full_word in ['--slave-interface']:
            candidates = self.manager.get_slave_candidates()
            return [c for c in candidates if c.startswith(text)]
        if last_full_word in [ '--stp', '--multicast-snooping', '--vlan-filtering']:
            return [s for s in ['yes', 'no'] if s.startswith(text)]

        options = [
            '--conn-name', '--bridge-ifname', '--slave-interface', '--stp',
            '--fdelay', '--stp-priority', '--no-clone-mac', '--multicast-snooping',
            '--vlan-filtering', '--vlan-default-pvid'
        ]
        return [opt for opt in options if opt.startswith(text)]

    def do_list_devices(self, _: str) -> None:
        """ List all available network devices. Alias: dev """
        self.manager.list_devices()

    def do_dev(self, arg: str) -> None:
        """Alias for list_devices."""
        return self.do_list_devices(arg)

    def do_list_connections(self, _: str) -> None:
        """ List all saved connection profiles. Alias: conn """
        self.manager.list_connections()

    def do_conn(self, arg: str) -> None:
        """ Alias for list_connections """
        return self.do_list_connections(arg)

    def do_list_bridges(self, _: str) -> None:
        """ Find and list all configured bridge connections. Alias: showb """
        found_bridges = self.manager.find_existing_bridges()
        if not found_bridges:
            print("No existing bridge connections found.")
        else:
            self.manager.show_existing_bridges(found_bridges)

    def do_show_bridges(self, arg: str) -> None:
        """ Alias for list_bridges """
        return self.do_list_bridges(arg)

    def _parse_name_or_uuid_arg(self, arg: str, command_name: str) -> Optional[tuple[str, bool]]:
        """Helper to parse a single name/UUID argument and a --dry-run flag."""
        args = arg.split()
        if not args:
            print(f"Error: {command_name} requires a connection name or UUID.")
            return None
        name_or_uuid = args[0]
        dry_run = '--dry-run' in args
        return name_or_uuid, dry_run

    def do_delete(self, arg: str) -> None:
        """
        Delete a connection by name or UUID.
        Usage: delete <name|uuid> [--dry-run]
        """
        parsed_args = self._parse_name_or_uuid_arg(arg, 'delete')
        if parsed_args:
            name_or_uuid, dry_run = parsed_args
            self.manager.delete_connection(name_or_uuid, True, dry_run)

    def complete_delete(self, text: str, _line: str, _begidx: str, _endidx: str) -> List[str]:
        """ complete delete command """
        return [i for i in self.manager.get_all_connection_identifiers() if i.startswith(text)]

    def do_activate(self, arg: str) -> None:
        """ Activate a connection by name or UUID. Usage: activate <name|uuid> """
        parsed_args = self._parse_name_or_uuid_arg(arg, 'activate')
        if parsed_args:
            name_or_uuid, dry_run = parsed_args
            self.manager.activate_connection(name_or_uuid, dry_run)

    def complete_activate(self, text: str, _line: str, _begidx: str, _endidx: str) -> List[str]:
        """ Complete activation """
        return [i for i in self.manager.get_all_connection_identifiers() if i.startswith(text)]

    def do_deactivate(self, arg: str) -> None:
        """ Deactivate a connection by name or UUID. Usage: activate <name|uuid> """
        parsed_args = self._parse_name_or_uuid_arg(arg, 'deactivate')
        if parsed_args:
            name_or_uuid, dry_run = parsed_args
            self.manager.deactivate_connection(name_or_uuid, dry_run)

    def complete_deactivate(self, text: str, _line: str, _begidx: str, _endidx: str) -> List[str]:
        """ Complete deactivation """
        return [i for i in self.manager.get_all_connection_identifiers() if i.startswith(text)]

    def do_exit(self, _: str) -> bool:
        """ Exit the interactive shell. Alias: quit """
        print("Goodbye!")
        return True

    def do_quit(self, arg: str) -> bool:
        """ Alias for exit """
        return self.do_exit(arg)


help_data = {
    'help_conn_name': 'The name for the new bridge connection profile (e.g., my-bridge).',
    'help_bridge_ifname': 'The name for the bridge network interface (e.g., br0).',
    'help_slave_interface': 'The existing physical interface to enslave (e.g., eth0).',
    'clone_mac': 'Do not set the bridge MAC address to be the same as the slave interface.',
    'stp': 'Enables or disables Spanning Tree Protocol (STP). Default: yes.',
    'stp_priority': 'Sets the STP priority (0-65535). Lower is more preferred.',
    'multicast_snooping': 'Enables or disables IGMP/MLD snooping. Default: yes.',
    'fdelay': 'Sets the STP forward delay in seconds (0-30).',
    'vlan_filtering': 'Enables or disables VLAN filtering on the bridge. Default: no',
    'vlan_default_pvid': 'Sets the default Port VLAN ID (1-4094) for the bridge port itself.',
}

def main():
    """ The main function """
    manager = NMManager()
    parser = argparse.ArgumentParser(description="Manage Bridge connections.")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    parser_add_bridge = subparsers.add_parser('add', help='Add a new bridge connection.')
    parser_add_bridge.add_argument(
        '-cn',
        '--conn-name',
        dest='conn_name',
        required=False,
        default=DEFAULT_BRIDGE_CONN_NAME,
        help=help_data['help_conn_name'],
    )
    parser_add_bridge.add_argument(
        '-bn',
        '--bridge-ifname',
        dest='bridge_ifname',
        default=DEFAULT_BRIDGE_IFNAME,
        required=False,
        help=help_data['help_bridge_ifname'],
    )
    parser_add_bridge.add_argument(
        '-i',
        '--slave-interface',
        dest='slave_interface',
        required=False,
        help=help_data['help_slave_interface']
    )
    parser_add_bridge.add_argument(
        '-ncm',
        '--no-clone-mac',
        dest='clone_mac',
        action='store_false',
        help=help_data['clone_mac']
    )
    parser_add_bridge.add_argument(
        '--stp',
        choices=['yes', 'no'],
        default='yes',
        help=help_data['stp']
    )
    parser_add_bridge.add_argument(
        '-sp',
        '--stp-priority',
        type=int,
        default=None,
        dest='stp_priority',
        help=help_data['stp_priority']
    )
    parser_add_bridge.add_argument(
        '-ms',
        '--multicast-snooping',
        choices=['yes', 'no'],
        default='yes',
        dest='multicast_snooping',
        help=help_data['multicast_snooping']
    )
    parser_add_bridge.add_argument(
        '--fdelay',
        type=int,
        default=None,
        dest='forward_delay',
        help=help_data['fdelay']
    )
    parser_add_bridge.add_argument(
        '--vlan-filtering',
        choices=['yes', 'no'],
        default='no',
        dest='vlan_filtering',
        help=help_data['vlan_filtering']
    )
    parser_add_bridge.add_argument(
        '-vdp',
        '--vlan-default-pvid',
        type=int,
        default=None,
        dest='vlan_default_pvid',
        help=help_data['vlan_default_pvid']
    )
    subparsers.add_parser('dev', help='Show all available network devices.')
    subparsers.add_parser('conn', help='Show all connections.')
    subparsers.add_parser('showb', help='Show all current bridges.')
    subparsers.add_parser('interactive', help='Start an interactive shell session.')
    parser.add_argument('-f', '--force', action='store_true',
                        help='Force adding a bridge (even if one exist already)'
                        )
    parser.add_argument('-dr', '--dry-run', dest='dry_run',
                        action='store_true', help='Dont do anything')
    parser_delete = subparsers.add_parser('delete', help='Delete a connection.')
    parser_delete.add_argument('name', help='The name (ID) or UUID of the connection to delete.')
    parser_activate = subparsers.add_parser('activate', help='Activate a connection.')
    parser_activate.add_argument('name',
                                help='The name (ID) or UUID of the connection to activate.'
                                )
    parser_deactivate = subparsers.add_parser('deactivate', help='Deactivate a connection.')
    parser_deactivate.add_argument('name',
                                    help='The name (ID) or UUID of the connection to deactivate.'
                                    )
    parser.add_argument('-d', '--debug',
                        action='store_true',
                        help='Enable debug mode (very verbose...)'
                        )

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    command_handler = CommandHandler(manager)
    command_handler.execute(args)

if __name__ == "__main__":
    if sys.version_info[0] < 3:
        logging.error("Must be run with Python 3")
        sys.exit(1)
    main()
