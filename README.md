# Network Bridge Creation Script (virt-bridge-setup)

Script to create a **bridge interface** on a specified interface or select one in automatic mode.
This was originally created to replace the automatic **yast2 virtualization** bridge creation.
This is a simple script which doesnt aim to support all network scenarios, for complex task please setup the bridge manually. Its preferable to run the script just after the installation, not after any network customisation. 
The script provides an **interactive mode** with **completion**.

## Command options

```bash
# virt-bridge-setup.py
usage: virt-bridge-setup.py [-h] [-f] [-d]
                            {add,dev,conn,showb,interactive,delete,activate,deactivate} ...

Manage Bridge connections.

positional arguments:
  {add,dev,conn,showb,interactive,delete,activate,deactivate}
                        Available commands
    add                 Add a new bridge connection.
    dev                 Show all available network devices.
    conn                Show all connections.
    showb               Show all current bridges.
    interactive         Start an interactive shell session.
    delete              Delete a connection.
    activate            Activate a connection.
    deactivate          Deactivate a connection.

options:
  -h, --help            show this help message and exit
  -f, --force           Force adding a bridge (even if one exist already)
  -d, --debug           Enable debug mode to show all commands executed

# virt-bridge-setup.py add --help
usage: virt-bridge-setup.py add [-h] [-cn CONN_NAME] [-bn BRIDGE_IFNAME] [-i SLAVE_INTERFACE]
                                [--no-clone-mac] [--stp {yes,no}] [--stp-priority STP_PRIORITY]
                                [--fdelay FDELAY]

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
  --stp-priority STP_PRIORITY
                        Set the STP priority (0-65535). Lower is more preferred.
  --fdelay FDELAY       Set the STP forward delay in seconds (e.g., 15).
```

In interactive mode use **[TAB]** key for completion.

```bash
# virt-bridge-setup.py interactive

Welcome to the interactive virt-bridge-setup shell.
Type `help` or `?` to list commands.

_________________________________________
virt-bridge #> [TAB]
activate          deactivate        exit              list_connections  show_bridges
add               delete            help              list_devices      
conn              dev               list_bridges      quit

virt-bridge #> list_devices
2025-09-24 19:47:05,379 - INFO - Querying for available devices...
INTERFACE       DEV TYPE     MAC ADDRESS          STATE           CONNECTION         AUTOCONNECT
=========================================================================================================
lo              VPRP         00:00:00:00:00:00    Activated       lo                 Yes         
enp1s0f0        Ethernet     C4:EF:XX:XX:XX:XX    Disconnected    ---                Yes         
wlp2s0          Wi-Fi        E6:5E:XX:XX:XX:XX    Disconnected    ---                Yes         
eth0            Ethernet     C4:EF:XX:XX:XX:XX    Activated       c-mybr0-port-eth0  Yes         
p2p-dev-wlp2s0  Wi-Fi P2P                         Disconnected    ---                Yes         
mybr0           Bridge       C4:EF:XX:XX:XX:XX    Activated       c-mybr0            Yes         
_________________________________________

virt-bridge #> show_bridges
--- Found 1 Bridge(s) ---
  Bridge Profile: c-mybr0
  |- Interface:    mybr0
  |- UUID:         f02247b5-19f8-XXXXXX-XXXXXXXX
  |- Slave(s):
  │  └─ eth0 (Profile: c-mybr0-port-eth0)
  |- IPv4 Config:  (auto)
  |  |- Address: 1X.X.X.XX/24
  |  |- Gateway: 1X.X.X.XX
  |   - DNS:     1X.X.X.XX
_________________________________________

virt-bridge #> add --[TAB]
--bridge-ifname    --fdelay           --slave-interface  --stp-priority     
--conn-name        --no-clone-mac     --stp              
_________________________________________

virt-bridge #> add --slave-interface [TAB]
enp1s0f0  eth0      wlp2s0    
_________________________________________

virt-bridge #> add --slave-interface [TAB]
enp1s0f0  eth0      wlp2s0    
_________________________________________

virt-bridge #> add --slave-interface eth0 --stp [TAB]
no   yes  
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
