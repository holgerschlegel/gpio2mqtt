# Main entry point of the GPIO2MQTT application
import argparse
import logging
import os
import signal
import sys
import threading
import time
import yaml

import gpio2mqtt
from .config import ConfigParser
from .device_pulse_counter import PulseCounter
from .devices import Device, Devices
from .mqtt import MqttConnection

_LOGGER = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    argparser = argparse.ArgumentParser(prog = "gpio2mqtt")
    argparser.add_argument("--debug", action = "store_true", help = "log debug information")
    argparser.add_argument("--version", action = "version", version = f"GPIO2MQTT version {gpio2mqtt.GPIO2MQTT_VERSION}")

    args = argparser.parse_args()
    logging.basicConfig(level = logging.DEBUG if args.debug else logging.INFO)
    return args


def _load_config_yaml(file: str) -> ConfigParser:
    """
    Loads the given yaml configuration file and returns a configuration parser for its content.

    Args:
        file (str): the configuration file to load
        logger (Logger, optional): the logger for error messages
    Returns:
        ConfigParser: the loaded configuration values, None if loading the file fails
    """
    _LOGGER.info("Loading configuration file %s", file)
    result = None
    try:
        with open(file, "r", encoding = "utf8") as stream:
            raw = yaml.safe_load(stream)
        result = ConfigParser(raw, _LOGGER)
    except FileNotFoundError:
        _LOGGER.critical("Configuration file %s not found", file)
    except yaml.YAMLError as error:
        _LOGGER.critical("Configuration file %s invalid: ", file, error)
    return result


def _get_device_classes() -> list[type[Device]]:
    # device classes must be passes as argument to Devices instance to break cyclic imports
    # for now, there is no need to dynamically scan for available devices classes
    return [ PulseCounter ]


def _setup_signals(exit_event: threading.Event, devices: Devices):
    def exit_handler(signum, frame):
        _LOGGER.info("Received signal '%s'. Shuting down GPIO2MQTT ...", signal.strsignal(signum))
        exit_event.set()
    signal.signal(signal.SIGINT, exit_handler)
    signal.signal(signal.SIGTERM, exit_handler)

    if devices.using_mock_gpio:
        _LOGGER.info("Installing signal handler to MOCK gpio input. Command to trigger: kill -s sigusr1 %s", os.getpid())
        def usr1_handler(signum, frame):
            _LOGGER.info("Received signal '%s'", signal.strsignal(signum))
            devices.mock_gpio_input()
        signal.signal(signal.SIGUSR1, usr1_handler)


def _loop(exit_event: threading.Event, devices: Devices) -> None:
    while not exit_event.is_set():
        try:
            devices.loop()
            time.sleep(1)
        except Exception as error:
            # try to recover from an unexpected exception by sleeping some time ...
            _LOGGER.error("Something went wrong, sleeping 60 seconds: %s", error)
            time.sleep(60)


def main() -> int: 
    _LOGGER.info("Starting GPIO2MQTT version %s ...", gpio2mqtt.GPIO2MQTT_VERSION)

    config: ConfigParser = _load_config_yaml(os.path.abspath("config.yaml"))
    if not config:
        return 1

    # create and start objects
    exit_event = threading.Event()
    mqtt = MqttConnection(config)
    devices = Devices(_get_device_classes(), config, mqtt)
    if config.has_errors:
        return 2

    if not mqtt.start():
        return 3
    devices.start()
    _setup_signals(exit_event, devices)
    _LOGGER.info("GPIO2MQTT started")

    # main loop
    _loop(exit_event, devices)

    # stop objects and clean up
    _LOGGER.info("Stopping GPIO2MQTT ...")
    devices.stop()
    mqtt.stop()
    _LOGGER.info("GPIO2MQTT stopped")
    return 0


# main entry point
args = _parse_args()
exit_code: int = main()
sys.exit(exit_code)
