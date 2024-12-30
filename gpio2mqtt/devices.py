"""
Base to manage devices.
"""
from abc import abstractmethod
import logging

from gpiozero import Device as GpiozeroDevice
from gpiozero.pins.mock import MockFactory

from . import GPIO2MQTT_VERSION
from .config import ConfigParser
from .mqtt import MqttConnection

_LOGGER = logging.getLogger(__name__)


class HomeAssistantInfo:
    """
    Holds informations for the Home Assistant MQTT auto discovery.
    """

    __slots__ = ("_enabled", "_name", "_component_names")


    def __init__(self, ha_config: ConfigParser):
        """
        Creates an instance from the given home assistant configuration.

        Args:
            ha_config (ConfigParser): the home assistant configuration
        """
        self._enabled: bool = ha_config.get_bool("enabled", default = True)
        self._name: str = ha_config.get_str("name", mandatory = self._enabled)
        self._component_names: dict[str, str] = {}
        for key in ha_config.raw:
            if key.endswith("_name"):
                self._component_names[key[:-5]] = ha_config.get_str(key)
        print(self._component_names)


    @property
    def enabled(self) -> bool:
        """
        Returns:
            str: True if the device is published to Home Assistant, False otherwise
        """
        return self._enabled


    @property
    def name(self) -> str:
        """
        Returns:
            str: the device name
        """
        return self._name


    def get_component_name(self, component_key: str, default: str) -> str:
        """
        Gets the friendly name for the component with the given key. Returns the given default if no name is set in
        the configuration.

        Args:
            component_key (str): the component key
            default (str): the default component name
        Returns:
            str: the component name
        """
        result: str = self._component_names.get(component_key, None)
        return result if result is not None else default


class Device():
    """
    Base class for devices.
    """

    def __init__(self, device_config: ConfigParser, mqtt: MqttConnection):
        """
        Creates an instance from the given device configuration.

        Args:
            device_config (ConfigParser): the device configuration
            mqtt (MqttConnection): the mqtt connection
        """
        self._id: str = device_config.get_str("id", mandatory = True, regex_pattern = "[a-zA-Z0-9_-]+")
        self._homeassistant: HomeAssistantInfo = HomeAssistantInfo(device_config.get_node_parser("homeassistant"))

        self._mqtt = mqtt
        self._state_topic: str = self._mqtt.base_topic + "/" + self.id


    @property
    def id(self) -> str:
        """
        Returns:
            str: the unique device id
        """
        return self._id


    @property
    def state_topic(self) -> str:
        """
        Returns:
            str: the device state topic
        """
        return self._state_topic


    @abstractmethod
    def start(self) -> None:
        """
        Starts the device.
        """


    @abstractmethod
    def stop(self) -> None:
        """
        Stops the device.
        """


    @abstractmethod
    def loop(self) -> None:
        """
        Invoked from the main loop. Devices may use it to publish the device values to MQTT. 
        """


    def mock_input(self) -> None:
        """
        Use for testing purpose only. Mocks/simulates an input on the device.
        """


    def publish_discovery(self) -> None:
        """
        Publishes the Home Assistant MQTT auto discovery message for this device.
        """
        if self._homeassistant:
            topic: str = self._mqtt.homeassistant_topic + "/device/gpio2mqtt/" + self.id + "/config"
            if self._homeassistant.enabled:
                payload: dict = self.get_discovery_payload()
                _LOGGER.info("Publishing Home Assistant discovery for %s with id %s: %s",
                        self.__class__.__name__, self.id, payload)
                self._mqtt.publish(topic, payload, retain = True)
            else:
                _LOGGER.info("Removing Home Assistant discovery for %s with id %s",
                        self.__class__.__name__, self.id)
                self._mqtt.publish(topic, None, as_json = False, retain = True)


    def get_discovery_payload(self) -> dict:
        """
        Gets the payload for Home Assistant MQTT auto discovery for this device.

        Returns:
            dict: _description_
        """
        payload: dict = {
            "device" : {
                "identifiers" : self.id,
                "name" : self._homeassistant.name,
                "manufacturer" : "GPIO2MQTT"
            },
            "origin" : {
                "name" : "GPIO2MQTT",
                "sw_version" : GPIO2MQTT_VERSION,
                "support_url" : "https://github.com/holgerschlegel/gpio2mqtt",
            },
            "availability" : {
                "topic": self._mqtt.bridge_state_topic,
                "value_template": "{{ value_json.state }}"
            },
            "state_topic" : self.state_topic,
            "components" : self.get_discovery_components()
        }
        return payload


    @abstractmethod
    def get_discovery_components(self) -> dict[str, dict]:
        """
        Invoked by get_discovery_payload to get the components for Home Assistant MQTT auto discovery.
        The returned dict must contain one entry for each component/entity with the component config as value.

        Returns:
            dict[str, dict]: the components
        """
        return None


    def get_discovery_component_config(self,
            platform: str,
            component_key: str,
            default_name: str,
            **kwargs
    ) -> dict[str, dict]:
        """
        Helper method to get the discovery config for a single component/entity of this device.
        The given component key is used to build the object_id and unique_id values and as key for the component in
        the returned dict.
        This method is meant to be used from get_discovery_components.

        Args:
            platform (str): the entity platform
            component_key (str): the component key
            default_name (str): the default component name
        Returns:
            dict[str, dict]: _description_
        """
        object_id: str = self.id + "_" + component_key
        config: dict = {
            "platform" : platform,
            "object_id" : object_id,
            "unique_id" : object_id,
            "name" : self._homeassistant.get_component_name(component_key, default_name),
        }
        config.update(kwargs)
        return { component_key : config }


class Devices:
    """
    Handles the devices.
    """

    def __init__(self, device_classes: list[type[Device]], config: ConfigParser, mqtt: MqttConnection):
        """
        Creates an instance.

        Args:
            device_classes (list[type[Device]]):
                    the available device classes, passes as argument to break cyclic imports
            config (ConfigParser): the application configuration
            mqtt (MqttConnection): the mqtt connection
        """
        self._device_classes: dict[str, type[Device]] = { clazz.__name__ : clazz for clazz in device_classes }
        self._devices = self._create_devices(config, mqtt)


    def start(self) -> None:
        """
        Starts the defined devices. Also publishes the Home Assistant auto discovery messages, if enabled.
        """
        for device in self._devices:
            device.start()
            device.publish_discovery()


    def stop(self) -> None:
        """
        Stops the defined devices.
        """
        for device in self._devices:
            device.stop()


    def loop(self) -> None:
        """
        Main loop callback for devices. Allows devices to do something periodically.
        """
        for device in self._devices:
            device.loop()


    @property
    def using_mock_gpio(self) -> bool:
        """
        Returns:
            bool: True if mock gpio is used, False otherwise
        """
        return isinstance(GpiozeroDevice.pin_factory, MockFactory)


    def mock_input(self) -> None:
        """
        Use for testing purpose only. Mocks/simulates a GPIO input on all devices.
        """
        for device in self._devices:
            device.mock_input()


    def _create_devices(self, config: ConfigParser, mqtt: MqttConnection) -> list[Device]:
        device_configs: list[ConfigParser] = config.get_list_parsers("devices", _LOGGER)
        known_types: set[str] = set(self._device_classes.keys())
        ids: set[str] = set()
        devices: list[Device] = []
        for device_config in device_configs:
            device_type: str = device_config.get_str("type", mandatory = True, allowed = known_types)
            if device_type is not None:
                device_class = self._device_classes.get(device_type)
                device = device_class(device_config, mqtt)
                device_config.check_unique("id", device.id, ids)
                if not device_config.has_errors:
                    devices.append(device)
                    _LOGGER.info("Created %s with id %s", device.__class__.__name__, device.id)
        return devices
