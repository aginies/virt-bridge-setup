#!/usr/bin/python3
# SUSE LLC
# aginies@suse.com
"""
script to create a bridge on an interface
This was previously done by yast2 virtualization
IPV4 only
"""
import subprocess
import argparse
import re
import logging
import time

# using the default name used previously by yast2
BRIDGE_INTERFACE = "br0"
MY_BRIDGE = "my-br0"

def run_command(cmd):
    """
    Launch a system command and log it if debug is enabled
    """
    logging.debug(f"Executing command: {cmd}")
    proc = subprocess.Popen(
        cmd, shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )
    try:
        out, errs = proc.communicate(timeout=25)
        return out.strip(), errs.strip()
    except subprocess.TimeoutExpired:
        proc.kill()
        out, errs = proc.communicate()
        return "", f"Command timed out: {cmd}\n{errs}"

def check_interface_exists(interface_name, connections_by_type):
    """
    check the interface choosen by the user exist
    """
    for _, connections in connections_by_type.items():
        for conn in connections:
            if conn['DEVICE'] == interface_name:
                return True
    return False

def is_networkmanager_running():
    """
    Check if NetworkManager is running using systemctl
    """
    cmd = "systemctl is-active NetworkManager"
    stdout, stderr = run_command(cmd)
    return stdout == "active", stdout + "\n" + stderr

def create_bridge(bridge_interface, interface, mac_address, conn_type, simple):
    """
    Create a new bridge and on an interface
    """
    _, stderr = run_command(
        f"nmcli connection add type bridge ifname {bridge_interface} con-name {MY_BRIDGE}"
    )
    if stderr:
        logging.error(f"Error adding bridge {bridge_interface}: {stderr}")
        return
    if simple is True:
        _, stderr = run_command(f"nmcli connection modify {interface} master {bridge_interface}")
    else:
        # work around a strange behavior of NetworkManager in SLE16 and TW
        _, stderr = run_command(f"nmcli connection add type {conn_type} ifname {interface} con-name {interface}-slave master {MY_BRIDGE}")
    if stderr:
        logging.error(f"Error add type {conn_type} ifname {interface}: {stderr}")
        return
    _, stderr = run_command(f"(nmcli connection modify {bridge_interface} bridge.mac-address {mac_address}")
    if stderr == "":
        logging.error(f"Error modify connection with MAC address: {mac_address}: {stderr}")
        return
    if stderr == "":
        logging.info(f"Slave interface: {interface}, Bridge Interface {bridge_interface} created")

def delete_bridge(bridge_interface, bridge_name):
    """
    delete bridge_name
    need --force
    """
    logging.warning(f"--force option used, deleting current bridge {bridge_name}")
    _, stderr = run_command(f"nmcli device delete {bridge_interface}")
    if stderr:
        logging.error(f"Error deleting bridge {bridge_interface}: {stderr}")
        return
    _, stderr = run_command(f"nmcli connection delete {bridge_name}")
    if stderr:
        logging.error(f"Error deleting id {bridge_name}: {stderr}")
        return

def bring_bridge_up(bridge_interface, interface):
    """
    Bring the bridge up and set it to autoconnect
    """
    logging.info(f"Bringing the bridge {bridge_interface} up, this can take some times...")
    #_, stderr = run_command(f"nmcli connection modify {MY_BRIDGE} ipv4.method auto")
    #if stderr:
    #    logging.error(f"Error modify {MY_BRIDGE} auto method: {stderr}")
    #    return
    run_command(f"nmcli connection modify {bridge_interface} connection.autoconnect yes")
    _, stderr = run_command(f"nmcli connection up {interface}-slave")
    if not wait_for_ip(bridge_interface):
        logging.error(f"Failed to obtain IP address on {bridge_interface}")
    if stderr:
        logging.error(f"Error bringing up {bridge_interface}: {stderr}")
        return

def wait_for_ip(interface, timeout=30, interval=5):
    """
    Wait for the interface to get an IP address
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        stdout, _ = run_command(f"nmcli device show {interface}")
        if re.search(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', stdout):
            logging.info(f"IP address obtained on {interface}: {stdout}")
            return True
        time.sleep(interval)
    return False

def get_nmcli_connection_info():
    """
    Get all connection info from nmcli command
    """
    cmd = ['nmcli', 'connection', 'show']

    nmcli_output = subprocess.check_output(cmd).decode('utf-8').strip()
    lines = nmcli_output.split('\n')
    headers = ['NAME', 'UUID', 'TYPE', 'DEVICE']
    connections_by_type = {}

    for line in lines[1:]:
        if line.strip():
            # to avoid any error name is everything before the UUID
            match = re.search(
                r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b',
                line)
            if match:
                uuid = match.group(0)
                connection_name = line[:match.start()].strip()
                parts = [connection_name, uuid, *line[match.end():].strip().split(maxsplit=1)]

                if len(parts) == 4:
                    connection_info = {headers[i]: parts[i] for i in range(len(headers))}
                    conn_type = connection_info['TYPE']
                    if conn_type not in connections_by_type:
                        connections_by_type[conn_type] = []
                    connections_by_type[conn_type].append(connection_info)

    return connections_by_type

def find_device(connections_by_type, target_types):
    """
    Find first device by type
    """
    for conn_type, connections in connections_by_type.items():
        if conn_type in target_types:
            print(connections)
            if '-' not in connections[0]['DEVICE']:
                return connections[0]['DEVICE']
    return None

def find_name(connections_by_type, interface):
    """
    find first connection name using interface name
    """
    for _, connections in connections_by_type.items():
        for conn in connections:
            if conn['DEVICE'] == interface:
                return connections[0]['NAME']
    return None

def find_mac(interface):
    """
    find the MAC address of the device
    """
    out, stderr = run_command(f"nmcli device show {interface} | grep GENERAL.HWADDR")
    if stderr:
        logging.error(f"Error finding MAC of {interface}: {stderr}")
        return None  # Return None if there's an error
    else:
        parts = out.split(':')
        if len(parts) == 2 and parts[0].strip() == "GENERAL.HWADDR":
            mac_address = parts[1].strip()
            return mac_address
        else:
            logging.error(f"Unexpected output format when getting MAC address for {interface}: {out}")
            return None

def find_type(connections_by_type, interface):
    """
    find type of connection using interface name
    """
    for _, connections in connections_by_type.items():
        for conn in connections:
            if conn['DEVICE'] == interface:
                return connections[0]['TYPE']
    return None
def main():
    """
    main programm
    """
    parser = argparse.ArgumentParser(description="Create a bridge on an interface. \
            By default it will choose first ethernet interface, if not present it \
            will pickup the first wireless one.")
    parser.add_argument('-i', '--interface', type=str, help='Specify the slave interface name')
    parser.add_argument('-f', '--force', action='store_true', help='Force deleting previous bridge')
    parser.add_argument('-c', '--complex', action='store_true', help='Force creating another interface as master')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug mode to show all commands executed')
    args = parser.parse_args()

    # Set up logging based on the --debug option
    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    if args.complex:
        simple = False
    else:
        simple = True

    status, output = is_networkmanager_running()
    if status:
        logging.info("NetworkManager is running.")
    else:
        logging.error("NetworkManager is not running. Exiting\nDetails:")
        logging.error(output)
        exit(1)

    connections_by_type = get_nmcli_connection_info()
    for conn_type, connections in connections_by_type.items():
        logging.debug(f"  {conn_type}:")
        for conn in connections:
            logging.debug(f"  UUID: {conn['UUID']}, NAME: {conn['NAME']}, DEVICE: {conn['DEVICE']}")

    bridge_interface = find_device(connections_by_type, ['bridge'])
    bridge_name = find_name(connections_by_type, bridge_interface)
    master_interface = args.interface or find_device(connections_by_type, ['ethernet']) or \
                      find_device(connections_by_type, ['wireless'])
    conn_type = find_type(connections_by_type, master_interface)
    conn_name = find_name(connections_by_type, master_interface)
    mac_address = find_mac(master_interface)
    logging.debug(f"bridge_interface: {bridge_interface} \
                  bridge_name: {bridge_name} \
                  master_interface: {master_interface} \
                  conn_type: {conn_type} \
                  #conn_name: {conn_name} \
                  mac_address: {mac_address} \
                  ")

    if bridge_interface:
        if args.force:
            delete_bridge(bridge_interface, bridge_name)
        else:
            logging.warning(f"Bridge {bridge_interface} already existing!")
            logging.info("You have 2 options:")
            logging.info("1) adjust your configuration with nmcli tool command line")
            logging.info(f"2) use --force to delete {bridge_interface} and setup another one")
            exit(1)

    if not master_interface:
        logging.error("No Ethernet or WiFi connection found. Adjust your network.")
        exit(1)

    if args.interface and not check_interface_exists(args.interface, connections_by_type):
        logging.error(f"Interface '{args.interface}' does not exist in the connections.")
        exit(1)

    create_bridge(BRIDGE_INTERFACE, master_interface, mac_address, conn_type, simple)
    bring_bridge_up(BRIDGE_INTERFACE, master_interface)

if __name__ == "__main__":
    main()
