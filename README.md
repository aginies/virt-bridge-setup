# Network Bridge Creation Script (virt-bridge-setup)

Script to create a **bridge interface** on a specified interface or select one in automatic mode.
This was originally created to replace the automatic **yast2 virtualization** bridge creation.
This is a simple script which doesnt aim to support all network scenarios, for complex task please setup the bridge manually. Its preferable to run the script just after the installation, not after any network customisation. 
The script provides an **interactive mode** with **completion**.

## Features

*   Create and manage bridge interfaces.
*   Command-line and interactive modes.
*   **Automatic slave interface selection**: If no slave interface is provided, the script will automatically select the best candidate (prioritizing active Ethernet, then active Wi-Fi).
*   Tab completion for commands and options in the interactive mode.
*   Support for various bridge options, including STP, VLAN, and more.
*   `--dry-run` mode to see what commands would be executed without making any changes.

## Prerequisites

- Python 3.x
- Python-dbus
- NetworkManager installed on the system

## Installation

Clone the repository:
```bash
git clone https://github.com/aginies/virt-bridge-setup.git
```

## Usage

### Global Options

| Option | Description |
| --- | --- |
| `-h`, `--help` | Show the help message and exit. |
| `-f`, `--force` | Force adding a bridge, even if one already exists. |
| `-dr`, `--dry-run` | Don't do anything, just show what would be done. |
| `-d`, `--debug` | Enable debug mode to show all commands executed. |

### Commands

| Command | Description |
| --- | --- |
| `add` | Add a new bridge connection. |
| `dev` | Show all available network devices. |
| `conn` | Show all connections. |
| `showb` | Show all current bridges. |
| `delete` | Delete a connection. |
| `activate` | Activate a connection. |
| `deactivate`| Deactivate a connection. |
| `interactive`| Start an interactive shell session. |

#### `add` command

The `add` command creates a new bridge connection.

| Option | Description | Default |
| --- | --- | --- |
| `-cn`, `--conn-name` | The name for the new bridge connection profile. | `c-mybr0` |
| `-bn`, `--bridge-ifname` | The name for the bridge network interface. | `mybr0` |
| `-i`, `--slave-interface` | The existing physical interface to enslave. | Automatic selection |
| `-ncm`, `--no-clone-mac` | Do not set the bridge MAC address to be the same as the slave interface. | `False` |
| `--stp` | Enables or disables Spanning Tree Protocol (STP). | `yes` |
| `-sp`, `--stp-priority` | Sets the STP priority (0-65535). Lower is more preferred. | `None` |
| `-ms`, `--multicast-snooping` | Enables or disables IGMP/MLD snooping. | `yes` |
| `--fdelay` | Sets the STP forward delay in seconds (0-30). | `None` |
| `--vlan-filtering` | Enables or disables VLAN filtering on the bridge. | `no` |
| `-vdp`, `--vlan-default-pvid` | Sets the default Port VLAN ID (1-4094) for the bridge port itself. | `None` |

### Interactive Mode

The interactive mode provides a shell to run the commands with tab completion.

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
  |- Bridge Settings:
  |  |- STP Enabled:   Yes
  |  |- STP Priority:  None
  |  |- Forward Delay: None
  |  |- IGMP snooping: Yes
  |  |- VLAN Filtering: No (Default)
  |   - MAC:    C4:EF:BB:A4:EF:E6
  |- IPv4 Config:  (auto)
  |  |- Address: 1X.X.X.XX/24
  |  |- Gateway: 1X.X.X.XX
  |   - DNS:     1X.X.X.XX
_________________________________________

virt-bridge #> add --[TAB]
--bridge-ifname       --multicast-snooping  --stp                 --vlan-filtering
--conn-name           --no-clone-mac        --stp-priority        
--fdelay              --slave-interface     --vlan-default-pvid   
_________________________________________

virt-bridge #> add --slave-interface [TAB]
enp1s0f0  eth0      wlp2s0    
_________________________________________

virt-bridge #> add --slave-interface eth0 --stp [TAB]
no   yes  
```

### Examples

**Create a bridge with automatic interface selection:**
```bash
# virt-bridge-setup.py add
```

**Create a bridge with a specific slave interface:**
```bash
# virt-bridge-setup.py add -i enp1s0f0
```

**Create a bridge with a custom name and disable STP:**
```bash
# virt-bridge-setup.py add -cn my-custom-bridge -bn br1 --stp no
```

**Show all bridges:**
```bash
# virt-bridge-setup.py showb
```

**Delete a bridge:**
```bash
# virt-bridge-setup.py delete my-custom-bridge
```

## Limits

* Tested only on IPv4 network
* This is a simple script not intended for complex network scenarios (vlan etc...); manual bridge setup is recommended for intricate configurations.
* The script should be run locally (not remotely) immediately after installation and before any custom network configurations.

## Licence

GPL2
