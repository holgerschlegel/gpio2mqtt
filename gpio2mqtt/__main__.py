"""
Main entry point of the GPIO2MQTT application.
"""
import argparse
import logging
import logging.config
import os
import signal
import sys
import threading
import time
import yaml

from . import GPIO2MQTT_VERSION
from .config import ConfigParser
from .device_pulse_counter import PulseCounter, ElectricityPulseMeter
from .devices import Device, Devices
from .mqtt import MqttConnection

_LOGGER = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    argparser = argparse.ArgumentParser(prog = "gpio2mqtt")
    argparser.add_argument("--logconsole", action = "store_true", help = "log to console instead of file")
    argparser.add_argument("--logdebug", action = "store_true", help = "log debug information")
    argparser.add_argument("--validate", action = "store_true", help = "validate config.yaml and exit")
    argparser.add_argument("--version", action = "version", version = f"GPIO2MQTT version {GPIO2MQTT_VERSION}")
    return argparser.parse_args()


def _setup_logging(logconsole: bool, logdebug: bool) -> None:
    dict_conf: dict = {
        "version" : 1,
        "disable_existing_loggers" : False,
        "formatters" : {
            "standard" : {
                "format" : "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
            }
        },
        "handlers" : {
            "console" : {
                "class" : "logging.StreamHandler",
                "formatter" : "standard",
                "stream" : sys.stdout
            },
            "file" : {
                "class" : "logging.handlers.RotatingFileHandler",
                "formatter" : "standard",
                "filename" : os.path.abspath("gpio2mqtt.log"),
                "maxBytes" : 1_000_000,
                "backupCount" : 5
            }
        },
        "root" : {
            "level" : logging.DEBUG if logdebug else logging.INFO,
            "handlers" : [ "console" if logconsole else "file" ]
        }
    }
    logging.config.dictConfig(dict_conf)


def _load_config_yaml(file: str) -> ConfigParser:
    _LOGGER.info("Loading configuration file '%s'", file)
    result = None
    try:
        with open(file, "r", encoding = "utf8") as stream:
            raw = yaml.safe_load(stream)
        result = ConfigParser(raw, _LOGGER)
    except FileNotFoundError:
        _LOGGER.critical("Configuration file '%s' not found", file)
    except yaml.YAMLError as error:
        _LOGGER.critical("Configuration file '%s' invalid: %s", file, error)
    return result


def _get_device_classes() -> list[type[Device]]:
    # device classes must be passes as argument to Devices instance to break cyclic imports
    # for now, there is no need to dynamically scan for available device classes
    return [ PulseCounter, ElectricityPulseMeter ]


def _setup_signals(exit_event: threading.Event, devices: Devices):
    def exit_handler(signum, frame): # pylint: disable=unused-argument
        _LOGGER.info("Received signal '%s'. Shuting down GPIO2MQTT ...", signal.strsignal(signum))
        exit_event.set()
    signal.signal(signal.SIGINT, exit_handler)
    signal.signal(signal.SIGTERM, exit_handler)

    if devices.using_mock_gpio:
        _LOGGER.info("Installing signal handler to MOCK gpio input. Command to trigger: kill -s sigusr1 %s",
                os.getpid())
        def usr1_handler(signum, frame): # pylint: disable=unused-argument
            _LOGGER.info("Received signal '%s'", signal.strsignal(signum))
            devices.mock_input()
        signal.signal(signal.SIGUSR1, usr1_handler)


def _loop(exit_event: threading.Event, devices: Devices) -> None:
    while not exit_event.is_set():
        try:
            devices.loop()
            time.sleep(1)
        except Exception as error: # pylint: disable=broad-exception-caught
            # try to recover from an unexpected exception by sleeping some time ...
            _LOGGER.error("Something went wrong, sleeping 60 seconds: %s", error)
            time.sleep(60)


def main(config_file: str, validate_config: bool) -> int:
    """
    Main entry point of the application.

    Args:
        config (ConfigParser): the configuration
    Returns:
        int: the exit code
    """
    _LOGGER.info("Starting GPIO2MQTT version %s ...", GPIO2MQTT_VERSION)

    config: ConfigParser = _load_config_yaml(config_file)
    if not config:
        return 2

    # create and start objects
    exit_event = threading.Event()
    mqtt = MqttConnection(config)
    devices = Devices(_get_device_classes(), config, mqtt)
    if config.has_errors:
        return 2
    if validate_config:
        _LOGGER.info("Configuration file '%s' is valid", config_file)
        return 0

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
args: argparse.Namespace = _parse_args()
_setup_logging(args.logconsole, args.logdebug)

exit_code: int = main(os.path.abspath("config.yaml"), args.validate)
sys.exit(exit_code)
