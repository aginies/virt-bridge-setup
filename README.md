# Network Bridge Creation Script (virt-bridge-setup)

This script allows you to create a network bridge on a specified interface using `nmcli`.
It simplifies the process of creating and managing network bridges for virtualization environments.
This was originally created to replace the automatic "yast2 virtualization" bridge creation.
Support IPV4 only.

## Features

- Checks if NetworkManager is running
- Creates a network bridge with the default name `br0`
- `-f` `--force`: deletes an existing bridge if used
- `-i` `--interface`: options to select the device
- `-s` `--simple`: Simple way to create the bridge
- `-n` `--norun`: Dry run
- `-m` `--mac`: Force using MAC address from the slave interface
- `-d` `--debug`: show debug info
- Activates the bridge and configures the connection to automatically connect

## Prerequisites

- Python 3.x
- `nmcli` (NetworkManager Command Line Interface)
- Subprocess module (included in Python standard library)

## Installation

Clone the repository:
```bash
git clone https://github.com/aginies/virt-bridge-setup.git
```

## Usage

```sh
python virt-bridge-setup.py -i <interface_name> [-f] [-d] [-s]
```

## Licence

GPL2
