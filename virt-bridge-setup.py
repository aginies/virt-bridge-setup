#!/usr/bin/python3
# SUSE LLC
# aginies@suse.com
"""
script to create a bridge on an interface
This was previously done by yast2 virtualization
"""
import subprocess
import argparse
import re

# using the default name used previously by yast2
BRIDGE_NAME = "br0"

def run_command(cmd):
    """
    Launch a system command
    """
    proc = subprocess.Popen(
        cmd, shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )
    try:
        out, errs = proc.communicate(timeout=5)
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

def create_bridge(bridge_name, interface_name):
    """
    Create a new bridge and on an interface
    """
    _, stderr = run_command(
        f"nmcli connection add type bridge ifname {bridge_name} con-name {bridge_name}"
        )
    if stderr:
        print(f"Error add bridge {bridge_name}: {stderr}")
        return
    _, stderr = run_command(f"nmcli connection modify {interface_name} master {bridge_name}")
    if stderr:
        print(f"Error modify master: {stderr}")
        return
    if stderr == "":
        print(f"Slave interface: {interface_name}, Bridge Interface {bridge_name} created")

def delete_bridge(bridge_name):
    """
    delete bridge_name
    need --force
    """
    print(f"--force option used, deleting current bridge {bridge_name}")
    _, stderr = run_command(f"nmcli connection delete {bridge_name}")
    if stderr:
        print(f"Error deleting bridge {bridge_name}: {stderr}")
        return

def bring_bridge_up(bridge_name, interface_name):
    """
    Bring the bridge up and set it to autoconnect
    """
    print(f"Bringing the bridge {bridge_name} up, this can take some times...")
    _, stderr = run_command(f"nmcli connection up {bridge_name}")
    if stderr:
        print(f"Error bringing up {bridge_name}: {stderr}")
        return
    # set interface_name up again to get the bridge up through this interface
    _, stderr = run_command(f"nmcli connection up {interface_name}")
    if stderr:
        print(f"Error bringing up {interface_name}: {stderr}")
        return
    run_command(f"nmcli connection modify {bridge_name} connection.autoconnect yes")

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

def find_connection(connections_by_type, target_types):
    """
    Find connection by type
    """
    for conn_type, connections in connections_by_type.items():
        if conn_type in target_types:
            return connections[0]['DEVICE']
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
    args = parser.parse_args()

    status, output = is_networkmanager_running()
    if status:
        print("NetworkManager is running.")
    else:
        print("NetworkManager is not running. Exiting\nDetails:")
        print(output)
        exit(1)

    connections_by_type = get_nmcli_connection_info()
    #for conn_type, connections in connections_by_type.items():
    #    print(f"  {conn_type}:")
    #    for conn in connections:
    #        print(f"    UUID: {conn['UUID']}, NAME: {conn['NAME']}, DEVICE: {conn['DEVICE']}")

    bridge_interface = find_connection(connections_by_type, ['bridge'])
    if bridge_interface:
        if args.force:
            delete_bridge(bridge_interface)
        else:
            print(f"Bridge {bridge_interface} already existing!")
            print("You have 2 options:")
            print("1) adjust your configuration with nmcli tool command line")
            print(f"2) use --force to delete {bridge_interface} and setup another one")
            exit(1)

    interface_name = args.interface or find_connection(connections_by_type, ['ethernet']) or \
                      find_connection(connections_by_type, ['wireless'])

    if not interface_name:
        print("No Ethernet or WiFi connection found. Adjust your network.")
        exit(1)

    if args.interface and not check_interface_exists(args.interface, connections_by_type):
        print(f"Interface '{args.interface}' does not exist in the connections.")
        exit(1)

    create_bridge(BRIDGE_NAME, interface_name)
    bring_bridge_up(BRIDGE_NAME, interface_name)

if __name__ == "__main__":
    main()
