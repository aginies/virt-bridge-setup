# Network Bridge Creation Script

This script allows you to create a network bridge on a specified interface using `nmcli`.
It simplifies the process of creating and managing network bridges for virtualization environments.
This was originally created to replace the automatic "yast2 virtualization" bridge creation.

## Features

- Checks if NetworkManager is running.
- Creates a network bridge with the default name `br0`.
- `--force` deletes an existing bridge if used.
- `--interface` options to select the device
- Activates the bridge and configures the connection to automatically connect.

## Prerequisites

- Python 3.x
- `nmcli` (NetworkManager Command Line Interface)
- Subprocess module (included in Python standard library)

## Installation

## Usage

```sh
python virt-bridge-setup.py -i <interface_name> [-f]
```

## Licence

GPL2
