import sys


def configure_console_output():
    """Keep redirected command output writable for Unicode mail and service names."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='backslashreplace')
