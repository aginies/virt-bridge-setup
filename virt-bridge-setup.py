#!/usr/bin/env python3
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

# Device types mapping
DEV_TYPES: Dict[int, str] = {
    0: "Unknown", 1: "Ethernet", 2: "Wi-Fi", 3: "WWAN", 4: "OLPC Mesh",
    5: "Bridge", 6: "Bluetooth", 7: "WiMAX", 8: "Modem", 9: "TUN",
    10: "InfiniBand", 11: "Bond", 12: "VLAN", 13: "ADSL", 14: "Team",
    15: "Generic", 16: "Veth", 17: "MACVLAN", 18: "OVS Port",
    19: "OVS Interface", 20: "Dummy", 21: "MACsec", 22: "IPVLAN",
    23: "OVS Bridge", 24: "IP Tunnel", 25: "Loopback", 26: "6LoWPAN",
    27: "HSR", 28: "Wi-Fi P2P", 29: "VRF", 30: "WireGuard",
    31: "WPAN", 32: "VPRP",
}

# Device states mapping
DEV_STATES: Dict[int, str] = {
    10: "Unmanaged", 20: "Unavailable", 30: "Disconnected", 40: "Prepare",
    50: "Config", 60: "Need Auth", 70: "IP Config", 80: "IP Check",
    90: "Secondaries", 100: "Activated", 110: "Deactivating", 120: "Failed",
}


class NMManager:
    """
    A class to manage NetworkManager via D-Bus.
    """

    def __init__(self) -> None:
        try:
            self.bus: dbus.SystemBus = dbus.SystemBus()
            self.nm_proxy: dbus.proxies = self.bus.get_object(
                'org.freedesktop.NetworkManager',
                '/org/freedesktop/NetworkManager'
            )
            self.nm_interface: dbus.proxies.Interface = dbus.Interface(
                self.nm_proxy,
                'org.freedesktop.NetworkManager'
            )
            self.nm_props_interface: dbus.proxies.Interface = dbus.Interface(
                self.nm_proxy,
                'org.freedesktop.DBus.Properties'
            )
            self.settings_proxy: dbus.proxies = self.bus.get_object(
                'org.freedesktop.NetworkManager',
                '/org/freedesktop/NetworkManager/Settings'
            )
            self.settings_interface: dbus.proxies.Interface = dbus.Interface(
                self.settings_proxy,
                'org.freedesktop.NetworkManager.Settings'
            )
        except dbus.exceptions.DBusException as err:
            logging.error("Error connecting to D-Bus: %s", err)
            logging.error("Please ensure NetworkManager is running.")
            sys.exit(1)
    def select_default_slave_interface(self) -> Optional[str]:
        """
        Selects a default slave interface, prioritizing active devices with IP addresses.
        """
        interface_lists: Dict[str, List[str]] = {
            'eth_with_ip': [], 'eth_without_ip': [],
            'wifi_with_ip': [], 'wifi_without_ip': []
        }

        try:
            devices_paths = self.nm_interface.GetAllDevices()
            for dev_path in devices_paths:
                dev_proxy = self.bus.get_object('org.freedesktop.NetworkManager', dev_path)
                prop_interface = dbus.Interface(dev_proxy, 'org.freedesktop.DBus.Properties')
                iface = prop_interface.Get('org.freedesktop.NetworkManager.Device', 'Interface')
                dev_type = prop_interface.Get('org.freedesktop.NetworkManager.Device', 'DeviceType')

                if iface == 'lo' or dev_type == 5 or any(iface.startswith(p) for p in ['virbr', 'vnet', 'docker', 'p2p-dev-']):
                    continue

                ip4_config_path = prop_interface.Get('org.freedesktop.NetworkManager.Device', 'Ip4Config')
                has_ip = False
                if ip4_config_path != "/":
                    ip4_config_proxy = self.bus.get_object('org.freedesktop.NetworkManager', ip4_config_path)
                    ip4_props_iface = dbus.Interface(ip4_config_proxy, 'org.freedesktop.DBus.Properties')
                    if ip4_props_iface.GetAll('org.freedesktop.NetworkManager.IP4Config').get('Addresses'):
                        has_ip = True

                if dev_type == 1:  # Ethernet
                    interface_lists['eth_with_ip' if has_ip else 'eth_without_ip'].append(iface)
                elif dev_type == 2:  # Wi-Fi
                    interface_lists['wifi_with_ip' if has_ip else 'wifi_without_ip'].append(iface)

        except dbus.exceptions.DBusException as err:
            logging.error("Error while selecting default interface: %s", err)
            return None

        for category in ['eth_with_ip', 'wifi_with_ip', 'eth_without_ip', 'wifi_without_ip']:
            if interface_lists[category]:
                selected_iface = sorted(interface_lists[category])[0]
                logging.info("Default slave interface selected: %s (%s)", selected_iface, category.replace('_', ' ').title())
                return selected_iface

        logging.warning("No suitable default slave interface was found.")
        return None

    def get_slave_candidates(self) -> List[str]:
        """ Returns a list of all potential slave interfaces (Ethernet, Wi-Fi) """
        candidates: List[str] = []
        try:
            devices_paths = self.nm_interface.GetAllDevices()
            for dev_path in devices_paths:
                dev_proxy = self.bus.get_object('org.freedesktop.NetworkManager', dev_path)
                prop_interface = dbus.Interface(dev_proxy, 'org.freedesktop.DBus.Properties')
                iface = prop_interface.Get('org.freedesktop.NetworkManager.Device', 'Interface')
                dev_type = prop_interface.Get('org.freedesktop.NetworkManager.Device', 'DeviceType')

                ignored_prefixes = ['lo', 'virbr', 'vnet', 'docker', 'p2p-dev-']
                if dev_type not in [1, 2] or dev_type == 5 or any(
                                    iface.startswith(p) for p in ignored_prefixes
                                    ):
                    continue
                candidates.append(iface)
        except dbus.exceptions.DBusException:
            return []
        candidates.sort()
        return candidates

    def find_existing_bridges(self) -> List[Dict[str, Any]]:
        """
        Finds all existing NetworkManager connections of type 'bridge'.
        """
        logging.debug("find_existing_bridges")
        # First, get all connection configurations
        all_connections_config = []
        connections_paths = self.settings_interface.ListConnections()
        for path in connections_paths:
            con_proxy = self.bus.get_object('org.freedesktop.NetworkManager', path)
            settings_connection = dbus.Interface(
                con_proxy,
                'org.freedesktop.NetworkManager.Settings.Connection'
            )
            all_connections_config.append(settings_connection.GetSettings())

        # Process all connections in one pass
        bridges_by_uuid = {}
        slaves_by_master_uuid: Dict[str, List[Dict[str, str]]] = {}

        for config in all_connections_config:
            conn_settings = config.get('connection', {})
            conn_type = conn_settings.get('type')
            conn_uuid = conn_settings.get('uuid')

            if conn_type == "bridge":
                if not conn_uuid:
                    continue
                bridge_details = {
                    'id': conn_settings.get('id', 'N/A'),
                    'uuid': conn_uuid,
                    'interface-name': conn_settings.get('interface-name', 'N/A'),
                    'slaves': [],
                    'ipv4': {},
                    'bridge_settings': {},
                }

                ipv4_config = config.get('ipv4', {})
                bridge_details['ipv4']['method'] = ipv4_config.get('method', 'disabled')
                bridge_details['ipv4']['addresses'] = [
                    f"{addr[0]}/{addr[1]}" for addr in ipv4_config.get('addresses', [])
                ]
                bridge_details['ipv4']['gateway'] = ipv4_config.get('gateway', None)
                bridge_details['ipv4']['dns'] = [str(d) for d in ipv4_config.get('dns', [])]

                bridge_config = config.get('bridge', {})
                mac_bytes = bridge_config.get('mac-address')
                vlan_setting = bridge_config.get('vlan-filtering')

                bridge_details['bridge_settings'] = {
                    'stp': 'Yes' if bridge_config.get('stp', True) else 'No',
                    'priority': bridge_config.get('priority'),
                    'forward-delay': bridge_config.get('forward-delay'),
                    'multicast-snooping': 'Yes' if bridge_config.get(
                            'multicast-snooping', True
                            ) else 'No',
                    'mac-address': ':'.join(
                            f'{b:02X}' for b in mac_bytes
                            ) if mac_bytes else 'Not set',
                    'vlan-filtering': 'Yes' if vlan_setting else 'No',
                    'vlan-default-pvid': bridge_config.get('vlan-default-pvid')
                }
                bridges_by_uuid[conn_uuid] = bridge_details

            elif conn_settings.get('slave-type') == 'bridge':
                master_uuid = conn_settings.get('master')
                if not master_uuid:
                    continue
                slave_details = {
                    'iface': conn_settings.get('interface-name', 'Unknown'),
                    'conn_id': conn_settings.get('id', 'Unknown Profile')
                }
                if master_uuid not in slaves_by_master_uuid:
                    slaves_by_master_uuid[master_uuid] = []
                slaves_by_master_uuid[master_uuid].append(slave_details)

        # Combine bridges with their slaves
        for suuid, bridge in bridges_by_uuid.items():
            if suuid in slaves_by_master_uuid:
                bridge['slaves'] = slaves_by_master_uuid[suuid]

        return list(bridges_by_uuid.values())

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
                print(f"  |   - vlan-default-pvid:    {b_settings['vlan-default-pvid']}")
            print(f"  |   - MAC:    {b_settings['mac-address']}")
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

    def add_bridge_connection(self, config: Dict[str, Any]) -> None:
        """ Creates a bridge and enslaves a physical interface to it """
        logging.debug("add_bridge_connection %s", config)
        bridge_conn_name = config['conn_name']
        bridge_ifname = config['bridge_ifname']
        slave_iface = config['slave_interface']
        stp = config.get('stp', 'yes')
        stp_priority = config.get('stp_priority', None)
        clone_mac = config.get('clone_mac', True)
        forward_delay = config.get('forward_delay', None)
        multicast_snooping = config.get('multicast_snooping', True)
        vlan_filtering = config.get('vlan_filtering', False)
        vlan_default_pvid = config.get('vlan_default_pvid', None)
        dry_run = config.get('dry_run', False)

        slave_conn_name = f"{bridge_conn_name}-port-{slave_iface}"

        self.delete_connection(bridge_conn_name, False, dry_run)
        self.delete_connection(slave_conn_name, False, dry_run)

        bridge_uuid = str(uuid.uuid4())
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
        if clone_mac:
            mac_address = self._get_mac_address(slave_iface)
            logging.info("MAC address of %s is %s", slave_iface, mac_address)
            if mac_address:
                mac_bytes = [int(x, 16) for x in mac_address.split(':')]
                bridge_settings['bridge']['mac-address'] = dbus.ByteArray(mac_bytes)

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

        if forward_delay is not None:
            if not 0 <= forward_delay <= 65535:
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
            bridge_settings['bridge']['vlan_default_pvid'] = dbus.UInt16(vlan_default_pvid)

        logging.debug("Bridge settings %s", bridge_settings)

        try:
            if dry_run is False:
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
            if dry_run is False:
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
            dev_proxy = self.bus.get_object('org.freedesktop.NetworkManager', dev_path)
            prop_interface = dbus.Interface(dev_proxy, 'org.freedesktop.DBus.Properties')

            ip4_config_path = prop_interface.Get(
                                        'org.freedesktop.NetworkManager.Device',
                                        'Ip4Config'
                                        )
            if ip4_config_path == "/":
                return None

            ip4_config_proxy = self.bus.get_object(
                                        'org.freedesktop.NetworkManager',
                                        ip4_config_path
                                        )
            ip4_props_iface = dbus.Interface(ip4_config_proxy, 'org.freedesktop.DBus.Properties')
            ip4_props = ip4_props_iface.GetAll('org.freedesktop.NetworkManager.IP4Config')

            addresses = []
            for addr_data in ip4_props.get('Addresses', []):
                ip_str = socket.inet_ntoa(struct.pack('<L', int(addr_data[0])))
                prefix = addr_data[1]
                addresses.append(f"{ip_str}/{prefix}")

            dns = [socket.inet_ntoa(struct.pack(
                                        '<L', int(d)
                                        )) for d in ip4_props.get('Nameservers', [])]
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
        devices = self.nm_interface.GetAllDevices()
        for dev_path in devices:
            dev_proxy = self.bus.get_object('org.freedesktop.NetworkManager', dev_path)
            prop_interface = dbus.Interface(dev_proxy, 'org.freedesktop.DBus.Properties')

            if prop_interface.Get(
                'org.freedesktop.NetworkManager.Device',
                'Interface') == iface_name:
                mac = prop_interface.Get('org.freedesktop.NetworkManager.Device', 'HwAddress')
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
            con_proxy = self.bus.get_object('org.freedesktop.NetworkManager', path)
            settings_connection = dbus.Interface(
                                        con_proxy,
                                        'org.freedesktop.NetworkManager.Settings.Connection'
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
                con_proxy = self.bus.get_object('org.freedesktop.NetworkManager', path)
                connection = dbus.Interface(
                    con_proxy,
                    'org.freedesktop.NetworkManager.Settings.Connection'
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

    def deactivate_connection(self, name_or_uuid: str, dry_run: bool = False) -> None:
        """ Deactivates a connection """
        logging.debug("deactivate_connection %s", name_or_uuid)
        active_connections = self.nm_props_interface.Get(
            'org.freedesktop.NetworkManager',
            'ActiveConnections'
        )
        active_conn_path_to_deactivate = None

        for path in active_connections:
            ac_proxy = self.bus.get_object('org.freedesktop.NetworkManager', path)
            prop_interface = dbus.Interface(ac_proxy, 'org.freedesktop.DBus.Properties')

            conn_settings_path = prop_interface.Get(
                                            'org.freedesktop.NetworkManager.Connection.Active',
                                            'Connection'
                                            )

            settings_proxy = self.bus.get_object(
                                    'org.freedesktop.NetworkManager',
                                    conn_settings_path
                                    )
            settings_iface = dbus.Interface(
                                    settings_proxy,
                                    'org.freedesktop.NetworkManager.Settings.Connection'
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
                logging.info("Successfully deactivated %s.", {name_or_uuid})
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
            con_proxy = self.bus.get_object('org.freedesktop.NetworkManager', path)
            settings_iface = dbus.Interface(
                con_proxy,
                'org.freedesktop.NetworkManager.Settings.Connection'
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
        print(f"{'NAME (ID)':<30} {'TYPE':<18} {'INTERFACE':<15} {'UUID'}")
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
        try:
            devices_paths = self.nm_interface.GetAllDevices()
            if not devices_paths:
                logging.error("No network devices found.")
                return False

            for dev_path in devices_paths:
                dev_proxy = self.bus.get_object('org.freedesktop.NetworkManager', dev_path)
                prop_interface = dbus.Interface(dev_proxy, 'org.freedesktop.DBus.Properties')
                iface = prop_interface.Get('org.freedesktop.NetworkManager.Device', 'Interface')
                if interface == iface:
                    return True  # Found it!

            return False

        except dbus.exceptions.DBusException as err:
            logging.error("Error getting interface: %s", err)
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
        try:
            devices_paths = self.nm_interface.GetAllDevices()
            if not devices_paths:
                logging.error("No network devices found.")
                return

            print(
                f"{'INTERFACE':<15} "
                f"{'DEV TYPE':<12} "
                f"{'MAC ADDRESS':<20} "
                f"{'STATE':<15} "
                f"{'CONNECTION':<18} "
                f"{'AUTOCONNECT':<10}"
                )
            print("=" * 105)

            for dev_path in devices_paths:
                dev_proxy = self.bus.get_object('org.freedesktop.NetworkManager', dev_path)
                prop_interface = dbus.Interface(dev_proxy, 'org.freedesktop.DBus.Properties')
                #all_props = prop_interface.GetAll('org.freedesktop.NetworkManager.Device')
                #dev_type_num = all_props['DeviceType']
                iface = prop_interface.Get('org.freedesktop.NetworkManager.Device', 'Interface')
                autoconnect_bool = prop_interface.Get(
                                                    'org.freedesktop.NetworkManager.Device',
                                                    'Autoconnect'
                                                    )
                autoconnect_str = "Yes" if autoconnect_bool else "No"
                dev_type_num = prop_interface.Get(
                                                'org.freedesktop.NetworkManager.Device',
                                                'DeviceType'
                                                )
                # WORKAROUND: Corrects known DeviceType bugs from certain NetworkManager versions.
                if dev_type_num == 13 and ('br' in iface or 'virbr' in iface):
                    logging.debug(
                                "Applying workaround: Correcting device type for %s from 13 to 5.",
                                iface
                                )
                    dev_type_num = 5
                elif dev_type_num == 30 and iface.startswith('p2p-dev-'):
                    logging.debug(
                        "Applying workaround: Correcting device type for %s from 30 to 28.",
                        iface
                        )
                    dev_type_num = 28
                dev_state_num = prop_interface.Get('org.freedesktop.NetworkManager.Device', 'State')
                mac_address = "---"
                try:
                    mac_address = prop_interface.Get(
                                                'org.freedesktop.NetworkManager.Device',
                                                'HwAddress'
                                                )
                except dbus.exceptions.DBusException:
                    pass

                active_conn_path = prop_interface.Get(
                                                'org.freedesktop.NetworkManager.Device',
                                                'ActiveConnection'
                                                )
                conn_name = "---"
                if active_conn_path != "/":
                    ac_proxy = self.bus.get_object(
                                                'org.freedesktop.NetworkManager',
                                                active_conn_path
                                                )
                    ac_props_iface = dbus.Interface(
                                                ac_proxy,
                                                'org.freedesktop.DBus.Properties'
                                                )
                    conn_settings_path = ac_props_iface.Get(
                                            'org.freedesktop.NetworkManager.Connection.Active',
                                            'Connection'
                                            )

                    settings_proxy = self.bus.get_object(
                                                    'org.freedesktop.NetworkManager',
                                                    conn_settings_path
                                                    )
                    settings_iface = dbus.Interface(
                                            settings_proxy,
                                            'org.freedesktop.NetworkManager.Settings.Connection'
                                            )
                    settings = settings_iface.GetSettings()
                    conn_name = settings['connection']['id']
                dev_type_str = DEV_TYPES.get(dev_type_num, f"Unknown ({dev_type_num})")
                dev_state_str = DEV_STATES.get(dev_state_num, f"Unknown ({dev_state_num})")
                print(
                    f"{iface:<15} "
                    f"{dev_type_str:<12} "
                    f"{mac_address:<20} "
                    f"{dev_state_str:<15} "
                    f"{conn_name:<18} "
                    f"{autoconnect_str:<12}"
                    )

        except dbus.exceptions.DBusException as err:
            logging.error("Error getting devices: %s", err)

class InteractiveShell(cmd.Cmd):
    """ A simple interactive shell to manage NetworkManager bridges """
    intro = "\nWelcome to the interactive virt-bridge-setup shell.\n"
    intro += "Type `help` or `?` to list commands.\n"
    promptline = '_________________________________________\n'
    prompt = promptline + "virt-bridge #> "

    def __init__(self, manager: 'NMManager') -> None:
        super().__init__()
        self.manager = manager
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
        parser = argparse.ArgumentParser(prog='add', description='Add a new bridge connection.')
        parser.add_argument('--conn-name', dest='conn_name', help=help_data['help_conn_name'],
                            default='c-mybr0')
        parser.add_argument('--bridge-ifname', dest='bridge_ifname',
                            help=help_data['help_bridge_ifname'],
                            default='mybr0')
        parser.add_argument('--slave-interface', dest='slave_interface',
                            help=help_data['slave_interface'])
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
        except SystemExit:
            return

        if not args.slave_interface:
            print("No slave interface provided. Selecting a default...")
            args.slave_interface = self.manager.select_default_slave_interface()
            if not args.slave_interface:
                print("Error: Could not find a suitable default slave interface.")
                return

        bridge_config = {
            'conn_name': args.conn_name,
            'bridge_ifname': args.bridge_ifname,
            'slave_interface': args.slave_interface,
            'clone_mac': args.clone_mac,
            'stp': args.stp,
            'forward_delay': args.forward_delay,
            'stp_priority': args.stp_priority,
            'multicast_snooping': args.multicast_snooping,
            'vlan_filtering': args.vlan_filtering,
            'vlan_default_pvid': args.vlan_default_pvid,
        }
        self.manager.add_bridge_connection(bridge_config)
        slave_conn_name = f"{args.conn_name}-port-{args.slave_interface}"
        self.manager.activate_connection(slave_conn_name)

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
    'slave_interface': 'The existing physical interface to enslave (e.g., eth0).',
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
        default="c-mybr0",
        help=help_data['help_conn_name'],
    )
    parser_add_bridge.add_argument(
        '-bn',
        '--bridge-ifname',
        dest='bridge_ifname',
        default="mybr0",
        required=False,
        help=help_data['help_bridge_ifname'],
    )
    parser_add_bridge.add_argument(
        '-i',
        '--slave-interface',
        dest='slave_interface',
        required=False,
        help=help_data['slave_interface']
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

    found_bridges = manager.find_existing_bridges()

    def handle_add_bridge(args):
        if found_bridges and not args.force:
            logging.info(
                "There is already some bridges on this system\n"
                "use --force option to create another one"
            )
            manager.show_existing_bridges(found_bridges)
            sys.exit(1)
        else:
            if not args.slave_interface:
                args.slave_interface = manager.select_default_slave_interface()
            if not manager.check_interface_exist(args.slave_interface):
                logging.error("No interface: %s", args.slave_interface)
                manager.list_devices()
                sys.exit(1)
            manager.add_bridge_connection(vars(args))
            slave_conn_name = f"{args.conn_name}-port-{args.slave_interface}"
            if not args.dry_run:
                manager.activate_connection(slave_conn_name)

    def handle_interactive(_):
        InteractiveShell(manager).cmdloop()
        sys.exit(0)

    def handle_dev(_):
        manager.list_devices()

    def handle_conn(_):
        manager.list_connections()

    def handle_delete(args):
        manager.delete_connection(args.name, True, args.dry_run)

    def handle_activate(args):
        manager.activate_connection(args.name, args.dry_run)

    def handle_deactivate(args):
        manager.deactivate_connection(args.name, args.dry_run)

    def handle_showb(_):
        if not found_bridges:
            logging.info("No existing bridge connections found.")
        else:
            manager.show_existing_bridges(found_bridges)

    command_handlers = {
        'add': handle_add_bridge,
        'interactive': handle_interactive,
        'dev': handle_dev,
        'conn': handle_conn,
        'delete': handle_delete,
        'activate': handle_activate,
        'deactivate': handle_deactivate,
        'showb': handle_showb,
    }

    if args.command in command_handlers:
        command_handlers[args.command](args)

if __name__ == "__main__":
    if sys.version_info[0] < 3:
        logging.error("Must be run with Python 3")
        sys.exit(1)
    main()
