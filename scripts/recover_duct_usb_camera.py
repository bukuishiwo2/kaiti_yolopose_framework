#!/usr/bin/env python3
"""Reset only the verified YLX video device while robot-rtsp is stopped."""
import fcntl
import os
from pathlib import Path
import subprocess


def main():
    device = Path('/sys/bus/usb/devices/1-3')
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo on the robot.')
    if device.joinpath('product').read_text().strip() != 'YLX-4K-S858':
        raise SystemExit('Unexpected USB product; refusing to reset.')
    bus = int(device.joinpath('busnum').read_text())
    number = int(device.joinpath('devnum').read_text())
    node = f'/dev/bus/usb/{bus:03d}/{number:03d}'
    subprocess.run(['systemctl', 'stop', 'robot-rtsp'], check=True)
    try:
        device.joinpath('power/control').write_text('on')
        with open(node, 'wb', buffering=0) as handle:
            fcntl.ioctl(handle, 0x5514, 0)  # USBDEVFS_RESET
        print(f'Reset YLX-4K-S858 at {node}', flush=True)
    finally:
        subprocess.run(['systemctl', 'start', '--no-block', 'robot-rtsp'], check=True)


if __name__ == '__main__':
    main()
