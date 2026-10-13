"""Portable terminal entry point for the unchanged, tuned console."""
import sys
import cartpole

DEFAULT_PORT = '/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00'


def main():
    args = sys.argv[1:]
    defaults = [] if '--text' in args else ['--text']
    if not any(arg.split('=', 1)[0] in ('--port', '--host') for arg in args):
        defaults += ['--port', DEFAULT_PORT]
    sys.argv = [sys.argv[0], *defaults, *args]
    cartpole.main()


if __name__ == '__main__':
    main()
