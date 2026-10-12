# virt-bridge-setup

**virt-bridge-setup** is a Python script that simplifies the creation and management of network bridge interfaces using NetworkManager via D-Bus. It can be run as a command-line tool or as an interactive shell.

This script was originally created to replace the automatic bridge creation of `yast2 virtualization`, but it can be used in any situation where you need to quickly set up a bridge interface.

## Table of Contents

- [Why use virt-bridge-setup?](#why-use-virt-bridge-setup)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
  - [Global Options](#global-options)
  - [Commands](#commands)
  - [Interactive Mode](#interactive-mode)
  - [Examples](#examples)
- [Limitations](#limitations)
- [Contributing](#contributing)
- [License](#license)

## Why use virt-bridge-setup?

Setting up a network bridge manually can be a tedious and error-prone process. This script automates the process and provides a simple and intuitive interface for creating and managing bridge interfaces.

It is especially useful for setting up virtual machines that need to be accessible from the local network.

## Features

- Create and manage bridge interfaces.
- Command-line and interactive modes.
- **Automatic slave interface selection**: If no slave interface is provided, the script will automatically select the best candidate (prioritizing active Ethernet, then active Wi-Fi).
- **Enhanced Interactive Mode**: A user-friendly interactive shell with wizards for creating, deleting, activating, and deactivating connections, reducing the need to memorize command-line arguments.
- Tab completion for commands and options in the interactive mode.
- Support for various bridge options, including STP, VLAN, and more.
- `--dry-run` mode to see what commands would be executed without making any changes.

## Prerequisites

- Python 3.x
- `dbus-python`
- NetworkManager

## Installation

1.  Clone the repository:

    ```bash
    git clone https://github.com/aginies/virt-bridge-setup.git
    ```

2.  Install the dependencies:

    ```bash
    pip install dbus-python
    ```

    Or, if you are using a package manager:

    ```bash
    # on openSUSE/SLES
    zypper install python3-dbus-python

    # on Debian/Ubuntu
    apt-get install python3-dbus

    # on Fedora/CentOS
    dnf install python3-dbus
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
| `-ncm`, `--no-clone-mac` | Do not set the bridge MAC address to be the same as the slave interface (a stable MAC is generated instead). | `False` |
| `--stp` | Enables or disables Spanning Tree Protocol (STP). | `yes` |
| `-sp`, `--stp-priority` | Sets the STP priority (0-65535). Lower is more preferred. | `None` |
| `-ms`, `--multicast-snooping` | Enables or disables IGMP/MLD snooping. | `yes` |
| `--fdelay` | Sets the STP forward delay in seconds (0-30). | `None` |
| `--vlan-filtering` | Enables or disables VLAN filtering on the bridge. | `no` |
| `-vdp`, `--vlan-default-pvid` | Sets the default Port VLAN ID (1-4094) for the bridge port itself. | `None` |

### Interactive Mode

The interactive mode provides a powerful shell to manage your bridges with ease. It features command completion and user-friendly wizards for common operations.

```bash
# virt-bridge-setup.py interactive

Welcome to the interactive virt-bridge-setup shell.
Type `help` or `?` to list commands.
```

#### Wizards for Easy Management

The interactive shell now includes wizards for the `add`, `delete`, `activate`, and `deactivate` commands. If you run these commands without any arguments, you will be guided through the process with interactive prompts.

**Example: The `add` wizard**

Typing `add` will start a step-by-step wizard to create a new bridge:

```
virt-bridge #> add
--- Interactive Bridge Creation ---
Connection name [c-mybr0]:
Bridge interface name [mybr0]:
Available slave interfaces:
  1: enp1s0f0
  2: wlp2s0
Select a slave interface (1-2): 1
Enable STP (yes/no) [yes]:
Clone MAC address from slave (yes/no) [yes]:

--- Configuration Summary ---
  Connection Name: c-mybr0
  Bridge Interface: mybr0
  Slave Interface: enp1s0f0
  Clone MAC: Yes
  STP Enabled: Yes

Proceed with creating the bridge? (yes/no) [yes]:
```

**Example: The `delete` wizard**

Typing `delete` will list all available connections and prompt you to select one to delete, with a confirmation step to prevent accidents.

```
virt-bridge #> delete
--- Interactive Connection Deletion ---
Available connections:
   1: c-mybr0                        (bridge)
   2: c-mybr0-port-enp1s0f0          (802-3-ethernet)
   3: Wired connection 1             (802-3-ethernet)
Select a connection to delete (1-3) (or press Enter to cancel): 1
Are you sure you want to delete 'c-mybr0'? (yes/no) [no]: yes
```

The `activate` and `deactivate` commands work in a similar way, providing a list of connections to choose from.

#### Command-Line and Tab Completion

For power users, commands still accept command-line arguments, and tab completion is available for all options.

**Listing devices:**
```
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
```

**Showing bridges:**
```
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
```

**Tab completion for `add` command:**
```
virt-bridge #> add --[TAB]
--bridge-ifname       --multicast-snooping  --stp                 --vlan-filtering
--conn-name           --no-clone-mac        --stp-priority
--fdelay              --slave-interface     --vlan-default-pvid

virt-bridge #> add --slave-interface [TAB]
enp1s0f0  eth0      wlp2s0

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

## Limitations

- Tested only on IPv4 network
- This is a simple script not intended for complex network scenarios (vlan etc...); manual bridge setup is recommended for intricate configurations.
- The script should be run locally (not remotely) immediately after installation and before any custom network configurations.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue.

## License

This project is licensed under the GPL-2.0 License. See the [LICENSE](LICENSE) file for details.
