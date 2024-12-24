import json
from gpiozero import LineSensor
import logging
import paho.mqtt.client as mqtt_client
from threading import RLock
import time
from typing import Final

from .config import ConfigParser
from .devices import Device
from .mqtt import MqttConnection
from . import utils

_LOGGER = logging.getLogger(__name__)

_INIT_MODE_MQTT: Final[str] = "mqtt"
_INIT_WAIT_MAX_SECONDS: Final[int] = 10


class PulseCounter(Device):
    """
    A simple pulse counter.
    """


    def __init__(self, device_config: ConfigParser, mqtt: MqttConnection) -> None:
        """
        Creates an instance from the given device configuration node.

        Args:
            device_config (ConfigParser): the device configuration
            mqtt (MqttConnection): the mqtt connection
        """
        super().__init__(device_config, mqtt)
        self._gpio_pin: int = device_config.get_int("gpio_pin", mandatory = True, min = 1, max = 40)
        self._active_high: bool = device_config.get_bool("active_high", mandatory = True)
        self._init_mode: str = device_config.get_str("init_mode", default = "new", allowed = { "new", _INIT_MODE_MQTT })
        self._publish_interval_seconds: int = device_config.get_int("publish_interval_seconds", mandatory = True, default = 0, min = 0)

        self._diff_count: int = None
        self._last_count: int = None
        self._last_time: float = None

        self._initializing: bool = False
        self._lock: RLock = RLock()


    def __str__(self):
        return f"PulseCounter(id={self._id}, name={self._name}," \
                " gpio_pin={self._gpio_pin}, active_high={self._active_high}," \
                " init_mode={self._init_mode}, publish_interval_seconds={self._publish_interval_seconds})"


    def start(self) -> None:
        # defined in class Device
        with self._lock:
            _LOGGER.info("Starting %s with id %s", self.__class__.__name__, self.id)
            self._init_state()
            self._init_sensor()
            self._start_command_handler()
            # TODO publish home assistant discovery config


    def stop(self) -> None:
        # defined in class Device
        with self._lock:
            self._stop_init_last_state()
            self._stop_command_handler()
            self._stop_sensor()
            if self._diff_count > 0:
                # publish last state to miss as few counts as possible in case of a restart
                self._publish_state(time.time())
            _LOGGER.info("Stopped %s with id %s", self.__class__.__name__, self.id)


    def loop(self) -> None:
        # defined in class Device
        with self._lock:
            now: float = time.time()
            diff_seconds: float = self._get_diff_seconds(now)

            if self._initializing and diff_seconds > _INIT_WAIT_MAX_SECONDS:
                # waited long enough, looks like there is no last state
                _LOGGER.debug("Waiting for last state timed out for %s with id %s", self.__class__.__name__, self.id)
                self._stop_init_last_state()
 
            if not self._initializing and self._check_loop_publish_state(diff_seconds):
                self._publish_state(now, diff_seconds)


    def get_count(self) -> int:
        """
        Gets the current total count.

        Returns:
            int: the total count
        """
        with self._lock:
            return self._last_count + self._diff_count


    def set_count(self, count: int, now: float = None) -> None:
        """
        Sets the current total count to the given value.

        Args:
            count (int): the total count
            now (float, optional): the time related to the total count, None to use now
        """
        with self._lock:
            if now is None:
                now = time.time()
            self._diff_count = 0
            self._last_count = count
            self._last_time = now
            self._publish_state(now, 0)


    def _get_diff_seconds(self, now: float) -> float:
        return round(now - self._last_time, 6)


    def _init_state(self) -> None:
        self._diff_count = 0
        self._last_count = 0
        self._last_time = time.time()
        if self._init_mode == _INIT_MODE_MQTT:
            # try to init last state from mqtt state topic
            self._initializing = True
            self._mqtt.add_message_handler(self.state_topic, self._on_init_last_state_message)


    def _stop_init_last_state(self) -> None:
        if self._initializing:
            self._initializing = False
            self._mqtt.remove_message_handler(self.state_topic, self._on_init_last_state_message)


    def _on_init_last_state_message(self, message: mqtt_client.MQTTMessage) -> None:
        with self._lock:
            if self._initializing:
                _LOGGER.info("Received last state message for %s with id %s: %s", self.__class__.__name__, self.id, message.payload)
                try:
                    payload: dict = json.loads(message.payload)
                    read_count: int = int(payload.get("count"))
                    read_time: float = utils.parse_iso_timestamp_tz(payload.get("timestamp"))
                    if read_count and read_time:
                        # message is valid, set last state but keep already counted pulses
                        self._last_count = read_count
                        self._last_time = read_time
                    else:
                        _LOGGER.error("Parsing last state message for %s with id %s failed: missing required values", self.__class__.__name__, self.id)
                except (ValueError, json.JSONDecodeError) as error:
                    _LOGGER.error("Parsing last state message for %s with id %s failed: %s", self.__class__.__name__, self.id, error)
                self._stop_init_last_state()


    def _init_sensor(self) -> None:
        self._sensor = LineSensor(self._gpio_pin, pull_up = not self._active_high)
        self._sensor.when_line = self._on_sensor_pulse


    def _stop_sensor(self) -> None:
        if self._sensor:
            self._sensor.close()
            self._sensor = None


    def _on_sensor_pulse(self) -> None:
        with self._lock:
            _LOGGER.debug("Input pulse for %s with id %s detected", self.__class__.__name__, self.id)
            self._diff_count += 1


    def mock_input(self) -> None:
        # defined in class Device
        self._on_sensor_pulse()


    def _start_command_handler(self) -> None:
        self._mqtt.add_message_handler(self.state_topic + "/set/count", self._on_set_count_message)


    def _stop_command_handler(self) -> None:
        self._mqtt.remove_message_handler(self.state_topic + "/set/count", self._on_set_count_message)


    def _on_set_count_message(self, message: mqtt_client.MQTTMessage) -> None:
        _LOGGER.info("Received set count command message for %s with id %s: %s", self.__class__.__name__, self.id, message.payload)
        try:
            read_count: int = int(message.payload.decode())
            if read_count:
                self.set_count(read_count)
        except (ValueError) as error:
            _LOGGER.error("Parsing set count command message for %s with id %s failed: %s", self.__class__.__name__, self.id, error)


    def _check_loop_publish_state(self, diff_seconds: float) -> bool:
        return self._diff_count > 0 and diff_seconds >= self._publish_interval_seconds


    def _publish_state(self, now: float, diff_seconds: float = None) -> None:
        if diff_seconds is None:
            diff_seconds = self._get_diff_seconds(now)
        payload: dict = self._get_publish_state_payload(now, diff_seconds)
        _LOGGER.debug("Publishing state for %s with id %s: %s", self.__class__.__name__, self.id, payload)
        if self._mqtt.publish(self.state_topic, payload, retain = True):
            self._last_count += self._diff_count
            self._last_time = now
            self._diff_count = 0


    def _get_publish_state_payload(self, now: float, diff_seconds: float) -> dict:
        payload: dict = { 
            "count" : self.get_count(),
            "timestamp" : utils.format_iso_timestamp_tz(now),
            "diff_count" : self._diff_count,
            "diff_seconds" : diff_seconds
        }
        return payload
