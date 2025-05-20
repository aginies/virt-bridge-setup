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

def create_bridge(bridge_interface, interface, conn_name, conn_type, simple):
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
        _, stderr = run_command(f"nmcli connection modify '{conn_name}' master {bridge_interface}")
    else:
        # work around a strange behavior of NetworkManager in SLE16 and TW
        _, stderr = run_command(f"nmcli connection add type {conn_type} ifname {interface} con-name {interface}-slave master {MY_BRIDGE}")
    if stderr:
        logging.error(f"Error add type {conn_type} ifname {interface}: {stderr}")
        return
    if stderr == "":
        logging.info(f"Slave interface: {interface}, Bridge Interface {bridge_interface} created")


def force_mac_address(bridge_name, mac_address):
    """
    force using mac address from slave interface
    """
    _, stderr = run_command(f"nmcli connection modify {bridge_name} bridge.mac-address {mac_address}")
    if stderr:
        logging.error(f"Error modify connection with MAC address: {mac_address}: {stderr}")
        return

def set_stp(bridge_name, stp_option):
    """
    STP yes or no
    """
    _, stderr = run_command(f"nmcli connection modify {bridge_name} bridge.stp {stp_option}")
    if stderr:
        logging.error(f"Error modify {bridge_name} bridge.stp {stp_option}: {stderr}")
        return

def set_fdelay(bridge_name, fdelay):
    """
    forward delay option
    """
    _, stderr = run_command(f"nmcli connection modify {bridge_name} bridge.forward-delay {fdelay}")
    if stderr:
        logging.error(f"Error modify {bridge_name} bridge.forward-delay {fdelay}: {stderr}")
        return

def delete_bridge(bridge_interface, bridge_name, interface):
    """
    delete bridge_name
    need --force
    """
    logging.warning(f"--force option used, deleting current bridge {bridge_name}")
    _, stderr = run_command(f"nmcli device delete {bridge_interface}")
    if stderr:
        logging.error(f"Error deleting bridge {bridge_interface}: {stderr}")
        return
    for name in [bridge_name, interface]:
        _, stderr = run_command(f"nmcli connection delete {name}")
        if stderr:
            logging.error(f"Error deleting id {name}: {stderr}")
            return

def bring_bridge_up(bridge_interface, interface, simple):
    """
    Bring the bridge up and set it to autoconnect
    """
    logging.info(f"Bringing the bridge {bridge_interface} up, this can take some times...")
    #_, stderr = run_command(f"nmcli connection modify {MY_BRIDGE} ipv4.method auto")
    #if stderr:
    #    logging.error(f"Error modify {MY_BRIDGE} auto method: {stderr}")
    #    return
    run_command(f"nmcli connection modify {MY_BRIDGE} connection.autoconnect yes")
    if simple is False:
        _, stderr = run_command(f"nmcli connection up {interface}-slave")
        if stderr:
            logging.error(f"Error bringing up {bridge_interface}: {stderr}")
            return
    else:
        _, stderr = run_command(f"nmcli connection up {MY_BRIDGE}")
        if stderr:
            logging.error(f"Error bringing up {MY_BRIDGE}: {stderr}")
            return


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
    out, stderr = run_command(f"nmcli -g GENERAL.HWADDR device show {interface}")
    if stderr:
        logging.error(f"Error finding MAC of {interface}: {stderr}")
        return None
    else:
        mac_address = out.replace("\\", "")
        return mac_address

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
    parser.add_argument('-s', '--simple', action='store_true', help='Simple way of creating the bridge')
    parser.add_argument('-m', '--mac', action='store_true', help='Force using MAC address from slave interface')
    parser.add_argument('--stp', type=str, help='Set STP to yes or no')
    parser.add_argument('--fdelay', type=int, help='Set forward-delay option (in second)')
    parser.add_argument('-n', '--norun', action='store_true', help='Dry run')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug mode to show all commands executed')
    args = parser.parse_args()

    # Set up logging based on the --debug option
    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    if args.simple:
        simple = True
    else:
        simple = False

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
    logging.debug(f"bridge_interface: {bridge_interface}\n \
                  bridge_name: {bridge_name}\n \
                  master_interface: {master_interface}\n \
                  conn_type: {conn_type}\n \
                  conn_name: {conn_name}\n \
                  mac_address: {mac_address}\n \
                  ")

    if bridge_interface:
        if args.force:
            delete_bridge(bridge_interface, bridge_name, master_interface+"-slave")
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

    if not args.norun:
        create_bridge(BRIDGE_INTERFACE, master_interface, conn_name, conn_type, simple)
        if args.mac:
            if simple is False:
                force_mac_address(MY_BRIDGE, mac_address)
            else:
                logging.info("Can't force MAC address in simple mode")
        if args.stp:
            if args.stp.lower() not in ['yes', 'no']:
                logging.error(f"{args.stp} is not yes or no")
                exit(1)
            set_stp(MY_BRIDGE, args.stp.lower())
        if args.fdelay:
            set_fdelay(MY_BRIDGE, args.fdelay)
        bring_bridge_up(BRIDGE_INTERFACE, master_interface, simple)

if __name__ == "__main__":
    main()
