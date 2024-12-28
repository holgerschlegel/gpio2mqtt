"""
Implementations of pulse counter devices.
"""
import json
import logging
from threading import RLock
import time
from typing import Final

from gpiozero import LineSensor
import paho.mqtt.client as mqtt_client

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
    Publishes the total "count" and the corresponding "timestamp".
    """


    def __init__(self, device_config: ConfigParser, mqtt: MqttConnection) -> None:
        """
        Creates an instance from the given device configuration node.

        Args:
            device_config (ConfigParser): the device configuration
            mqtt (MqttConnection): the mqtt connection
        """
        super().__init__(device_config, mqtt)
        self._gpio_pin: int = device_config.get_int("gpio_pin", mandatory = True, min_value = 1, max_value = 40)
        self._active_high: bool = device_config.get_bool("active_high", mandatory = True)
        self._init_mode: str = device_config.get_str("init_mode", default = "new", allowed = { "new", _INIT_MODE_MQTT })
        self._publish_interval_seconds: int = device_config.get_int("publish_interval_seconds",
                mandatory = True, default = 0, min_value = 0)
        self._count_name: str = device_config.get_str("count_name", default = "Count")
        self._timestamp_name: str = device_config.get_str("timestamp_name", default = "Timestamp")

        self._count: int = None
        self._published_count: int = None
        self._published_time: float = None

        self._sensor = None
        self._initializing: bool = False
        self._lock: RLock = RLock()


    def start(self) -> None:
        with self._lock:
            _LOGGER.info("Starting %s with id %s", self.__class__.__name__, self.id)
            self._init_state()
            self._init_sensor()
            self._start_command_handler()


    def stop(self) -> None:
        with self._lock:
            self._stop_init_last_state()
            self._stop_command_handler()
            self._stop_sensor()
            if self._count > self._published_count:
                # publish last state to miss as few counts as possible in case of a restart
                self._publish_state(time.time())
            _LOGGER.info("Stopped %s with id %s", self.__class__.__name__, self.id)


    def loop(self) -> None:
        with self._lock:
            now: float = time.time()
            diff_seconds: float = now - self._published_time

            if self._initializing and diff_seconds > _INIT_WAIT_MAX_SECONDS:
                # waited long enough, looks like there is no last state
                _LOGGER.debug("Waiting for last state timed out for %s with id %s", self.__class__.__name__, self.id)
                self._stop_init_last_state()

            if not self._initializing and self._count > self._published_count \
                    and diff_seconds >= self._publish_interval_seconds:
                self._publish_state(now)


    def get_count(self) -> int:
        """
        Gets the current count.

        Returns:
            int: the count
        """
        with self._lock:
            return self._count


    def set_count(self, count: int, now: float = None) -> None:
        """
        Sets the current count to the given value. Publishes the new state.

        Args:
            count (int): the count
            now (float, optional): the time related to the count, None to use now
        """
        with self._lock:
            if now is None:
                now = time.time()
            self._count = count
            self._published_count = count
            self._published_time = now
            self._publish_state(now)


    def _init_state(self) -> None:
        self._count = 0
        self._published_count = 0
        self._published_time = time.time()
        if self._init_mode == _INIT_MODE_MQTT:
            self._initializing = True
            self._mqtt.add_message_handler(self.state_topic, self._on_init_last_state_message)


    def _stop_init_last_state(self) -> None:
        if self._initializing:
            self._initializing = False
            self._mqtt.remove_message_handler(self.state_topic, self._on_init_last_state_message)


    def _on_init_last_state_message(self, message: mqtt_client.MQTTMessage) -> None:
        with self._lock:
            if self._initializing:
                _LOGGER.info("Received last state message for %s with id %s: %s",
                        self.__class__.__name__, self.id, message.payload)
                try:
                    payload: dict = json.loads(message.payload)
                    read_count: int = int(payload.get("count"))
                    read_time: float = utils.parse_iso_timestamp_tz(payload.get("timestamp"))
                    if read_count and read_time:
                        # message is valid, set last state but keep pulses counted since start
                        self._count += read_count
                        self._published_count = read_count
                        self._published_time = read_time
                    else:
                        _LOGGER.error("Parsing last state message for %s with id %s failed: missing required values",
                                self.__class__.__name__, self.id)
                except (ValueError, json.JSONDecodeError) as error:
                    _LOGGER.error("Parsing last state message for %s with id %s failed: %s",
                            self.__class__.__name__, self.id, error)
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
            self._count += 1


    def mock_input(self) -> None:
        self._on_sensor_pulse()


    def _start_command_handler(self) -> None:
        self._mqtt.add_message_handler(self.state_topic + "/set/count", self._on_set_count_message)


    def _stop_command_handler(self) -> None:
        self._mqtt.remove_message_handler(self.state_topic + "/set/count", self._on_set_count_message)


    def _on_set_count_message(self, message: mqtt_client.MQTTMessage) -> None:
        _LOGGER.info("Received set count command message for %s with id %s: %s",
                self.__class__.__name__, self.id, message.payload)
        try:
            read_count: int = int(message.payload.decode())
            if read_count:
                self.set_count(read_count)
        except (ValueError) as error:
            _LOGGER.error("Parsing set count command message for %s with id %s failed: %s",
                    self.__class__.__name__, self.id, error)


    def _publish_state(self, now: float) -> None:
        payload: dict = self._get_publish_state_payload(now)
        _LOGGER.debug("Publishing state for %s with id %s: %s", self.__class__.__name__, self.id, payload)
        if self._mqtt.publish(self.state_topic, payload, retain = True):
            self._published_count = self._count
            self._published_time = now


    def _get_publish_state_payload(self, now: float) -> dict:
        payload: dict = {
            "count" : self._count,
            "timestamp" : utils.format_iso_timestamp_tz(now)
        }
        return payload


    def get_discovery_component_defaults(self) -> dict[str, str]:
        return {
            "count" : "Count",
            "timestamp" : "Timestamp"
        }


    def get_discovery_components(self) -> dict[str, dict]:
        components: dict[str, dict] = {}
        components.update(self.get_discovery_component_config("sensor", "count",
                icon = "mdi:counter", state_class = "total_increasing", value_template = "{{ value_json.count }}"))
        components.update(self.get_discovery_component_config("sensor", "timestamp",
                enabled_by_default = False, device_class = "timestamp", value_template = "{{ value_json.timestamp }}"))
        return components


class ElectricityPulseMeter(PulseCounter):
    """
    An pulse counter based electricity meter.
    In additiom to the values of the Pulse Counter, this devices publishes the "energy" (in kWh) and the current
    "power" (in W).
    """

    def __init__(self, device_config: ConfigParser, mqtt: MqttConnection) -> None:
        """
        Creates an instance from the given device configuration node.

        Args:
            device_config (ConfigParser): the device configuration
            mqtt (MqttConnection): the mqtt connection
        """
        super().__init__(device_config, mqtt)
        self._pulses_per_kwh: int = device_config.get_int("pulses_per_kwh", mandatory = True,
                min_value = 1, max_value = 10_000)

        self._pulse_time: float = None
        self._pulse_seconds: float = None

        # factor to calculate power in W from diff_count and diff_seconds
        # count * pulses_per_kwh => kWh, devide by hours (seconds / 3600), multiply by 1000 (kW -> W)
        self._power_calc_factor = 3_600_000 / self._pulses_per_kwh


    def get_energy(self) -> float:
        """
        Gets the current total energy in kWh. The result is calculated from the current total pulse count.

        Returns:
            float: the energy in kWh
        """
        return round(self.get_count() / self._pulses_per_kwh, 1)


    def set_energy(self, energy: float, now: float = None) -> None:
        """
        Sets the current total energy in kWh to the given value. Calculates and sets the corresponding total pulse
        count. Publishes the new state.

        Args:
            energy (float): the energy in kWh
            now (float, optional): the time related to the total energy, None to use now
        """
        self.set_count(int(energy * self._pulses_per_kwh), now)


    def get_power(self) -> float | None:
        """
        Gets the current power in W. The result is calculated from the time between the last two counted pulses.

        Returns:
            float | None: the current power in W, None if not available
        """
        power: float = None
        if self._pulse_seconds is not None:
            power = round(self._power_calc_factor / self._pulse_seconds, 1)
        return power


    def _init_state(self) -> None:
        self._pulse_time = None
        self._pulse_seconds = None
        super()._init_state()


    def _on_sensor_pulse(self) -> None:
        with self._lock:
            super()._on_sensor_pulse()
            # duration between the last two pulse is used to calculate current power
            now: float = time.time()
            if self._pulse_time is None:
                self._pulse_time = now
            else:
                self._pulse_seconds = now - self._pulse_time
                self._pulse_time = now


    def _start_command_handler(self):
        super()._start_command_handler()
        self._mqtt.add_message_handler(self.state_topic + "/set/energy", self._on_set_energy_message)


    def _stop_command_handler(self):
        super()._stop_command_handler()
        self._mqtt.remove_message_handler(self.state_topic + "/set/energy", self._on_set_energy_message)


    def _on_set_energy_message(self, message: mqtt_client.MQTTMessage) -> None:
        _LOGGER.info("Received set energy command message for %s with id %s: %s",
                self.__class__.__name__, self.id, message.payload)
        try:
            read_energy: int = int(message.payload.decode())
            if read_energy:
                self.set_energy(read_energy)
        except (ValueError) as error:
            _LOGGER.error("Parsing set energy command message for %s with id %s failed: %s",
                    self.__class__.__name__, self.id, error)


    def _get_publish_state_payload(self, now):
        payload: dict = super()._get_publish_state_payload(now)
        payload["energy"] = self.get_energy()
        payload["power"] = self.get_power()
        return payload


    def get_discovery_component_defaults(self) -> dict[str, str]:
        defaults: dict[str, str] = super().get_discovery_component_defaults()
        defaults.update({
            "energy" : "Energy",
            "power" : "Power"
        })
        return defaults


    def get_discovery_components(self):
        components: dict[str, dict] = super().get_discovery_components()
        # hide component "count" created by base class PulseCounter
        components["count"]["enabled_by_default"] = False

        components.update(self.get_discovery_component_config("sensor", "energy",
                device_class = "energy", unit_of_measurement = "kWh",
                state_class = "total_increasing", value_template = "{{ value_json.energy }}"))
        components.update(self.get_discovery_component_config("sensor", "power",
                device_class = "power", unit_of_measurement = "W", value_template = "{{ value_json.power }}"))
        return components
