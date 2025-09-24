# Network Bridge Creation Script (virt-bridge-setup)

This script allows you to create a network bridge on a specified interface.
It simplifies the process of creating and managing network bridges for virtualization environments.
This was originally created to replace the automatic "yast2 virtualization" bridge creation.
This is a simple script which doesnt aim to support all network scenarios, for complex task please setup the bridge manually. Its preferable to run the script just after the installation, not after any network customisation.

## Command options

```bash
# virt-bridge-setup.py
usage: virt-bridge-setup.py [-h] [-f] [-d] {add,dev,conn,showb,delete,activate,deactivate} ...

Manage Bridge connections.

positional arguments:
  {add,dev,conn,showb,delete,activate,deactivate}
                        Available commands
    add                 Add a new bridge connection.
    dev                 Show all available network devices.
    conn                Show all connections.
    showb               Show all current bridges.
    delete              Delete a connection.
    activate            Activate a connection.
    deactivate          Deactivate a connection.

options:
  -h, --help            show this help message and exit
  -f, --force           Force adding a bridge (even if one exist already)
  -d, --debug           Enable debug mode to show all commands executed

# virt-bridge-setup.py add --help
usage: virt-bridge-setup.py add [-h] [-cn CONN_NAME] [-bn BRIDGE_IFNAME] -i SLAVE_INTERFACE
                                [--no-clone-mac] [--stp {yes,no}] [--fdelay FDELAY]

options:
  -h, --help            show this help message and exit
  -cn, --conn-name CONN_NAME
                        The name for the new bridge connection profile (e.g., my-bridge).
  -bn, --bridge-ifname BRIDGE_IFNAME
                        The name for the bridge network interface (e.g., br0).
  -i, --slave-interface SLAVE_INTERFACE
                        The existing physical interface to enslave (e.g., eth0).
  --no-clone-mac        Do not set the bridge MAC address to be the same as the slave interface.
  --stp {yes,no}        Enable or disable Spanning Tree Protocol (STP). Default: yes.
  --fdelay FDELAY       Set the STP forward delay in seconds (e.g., 15).
```

## Limits

* Tested only on IPv4 network
* This is a simple script not intended for complex network scenarios (vlan etc...); manual bridge setup is recommended for intricate configurations.
* The script should be run locally (not remotely) immediately after installation and before any custom network configurations.

## Prerequisites

- Python 3.x
- Python-dbus
- NetworkManager installed on the system

## Installation

Clone the repository:
```bash
git clone https://github.com/aginies/virt-bridge-setup.git
```

## Licence

GPL2
