from datetime import datetime
import json
import logging
import paho.mqtt.client as mqtt_client
from threading import Lock

try:
    import RPi.GPIO as GPIO # type: ignore
except:
    import Mock.GPIO as GPIO

from .config import ConfigParser
from .devices import Device
from .mqtt import MqttConnection

_LOGGER = logging.getLogger(__name__)


class PulseCounter(Device):
    """
    A simple pulse counter.
    """

    def __init__(self, device_config: ConfigParser, mqtt: MqttConnection):
        """
        Creates an instance from the given device configuration node.

        Args:
            device_config (ConfigParser): the device configuration
            mqtt (MqttConnection): the mqtt connection
        """
        super().__init__(device_config, mqtt)
        self._gpio_channel: int = device_config.get_int("gpio_channel", mandatory = True, min = 1, max = 40)
        self._gpio_debounce_millis: int = device_config.get_int("gpio_debounce_millis", mandatory = True, default = 0, min = 0)
        self._count_high: bool = device_config.get_bool("count_high", mandatory = True, default = True)
        self._publish_interval_seconds: int = device_config.get_int("publish_interval_seconds", mandatory = True, default = 0, min = 0)

        self._count: int = None
        self._last_count: int = None
        self._last_datetime: datetime = None
        self._fetch_last_state: bool = False

        self._lock: Lock = Lock()


    def start(self) -> None:
        # defined in class Device
        _LOGGER.info("Starting %s with id %s", self.__class__.__name__, self.id)
        self._count = 0
        self._last_count = 0
        self._last_datetime = datetime.now()

        self._gpio_setup()
        self._start_fetch_last_state()
        # TODO publish home assistant config


    def stop(self) -> None:
        # defined in class Device
        GPIO.remove_event_detect(self._gpio_channel)
        self._stop_fetch_last_state()
        _LOGGER.info("Stopped %s with id %s", self.__class__.__name__, self.id)


    def loop(self) -> None:
        # defined in class Device
        with self._lock:
            diff_count: int = self._count - self._last_count
            now: datetime = datetime.now()
            diff_seconds: int = int((now - self._last_datetime).total_seconds())

            if self._fetch_last_state and diff_seconds > 30:
                # waited long enough, looks like there is no published last state ...
                _LOGGER.debug("Waiting for last state message timed out for %s with id %s", self.__class__.__name__, self.id)
                self._stop_fetch_last_state()

            if not self._fetch_last_state and self._check_publish_state(diff_count, diff_seconds):
                _LOGGER.debug("Publishing state for %s with id %s", self.__class__.__name__, self.id)
                payload: dict = self._get_publish_state_payload(now, diff_count, diff_seconds)
                if self._mqtt.publish(self.state_topic, payload, retain = True):
                    self._last_count = self._count
                    self._last_datetime = now


    def _check_publish_state(self, diff_count: int, diff_seconds: int) -> bool:
        return diff_count > 0 and diff_seconds >= self._publish_interval_seconds


    def _get_publish_state_payload(self, now: datetime, diff_count: int, diff_seconds: int) -> dict:
        payload: dict = { 
            "count" : self._count,
            "datetime" : now.isoformat(timespec = "seconds"),
            "diff_count" : diff_count,
            "diff_seconds" : diff_seconds
        }
        return payload


    def _start_fetch_last_state(self) -> None:
        self._fetch_last_state = True
        self._mqtt.add_message_handler(self.state_topic, self._on_fetch_last_state_message)


    def _stop_fetch_last_state(self) -> None:
        if self._fetch_last_state:
            self._fetch_last_state = False
            self._mqtt.remove_message_handler(self.state_topic, self._on_fetch_last_state_message)


    def _on_fetch_last_state_message(self, message: mqtt_client.MQTTMessage) -> None:
        with self._lock:
            if self._fetch_last_state:
                _LOGGER.info("Received last state message for %s with id %s: %s", self.__class__.__name__, self.id, message.payload)
                try:
                    payload: dict = json.loads(message.payload)
                    read_count: int = int(payload.get("count"))
                    read_datetime: datetime = datetime.fromisoformat(payload.get("datetime"))
                    # all values has been read without error, use it
                    self._last_count = read_count
                    self._last_datetime = read_datetime
                    self._count += read_count
                except (ValueError, json.JSONDecodeError) as error:
                    _LOGGER.error("Parsing last state message for %s with id %s failed: %s", self.__class__.__name__, self.id, error)
                self._stop_fetch_last_state()


    def _gpio_setup(self) -> None:
        if self._count_high:
            pull_up_down = GPIO.PUD_DOWN
            edge = GPIO.RISING
        else:
            pull_up_down = GPIO.PUD_UP
            edge = GPIO.FALLING
        GPIO.setup(self._gpio_channel, GPIO.IN, pull_up_down)
        GPIO.add_event_detect(self._gpio_channel, edge, self._gpio_callback, bouncetime = self._gpio_debounce_millis)


    def _gpio_callback(self, channel) -> None:
        with self._lock:
            _LOGGER.debug("GPIO input for %s with id %s on channel %d", self.__class__.__name__, self.id, channel)
            self._count += 1


    def mock_gpio_input(self) -> None:
        # defined in class Device
        self._gpio_callback(self._gpio_channel)
