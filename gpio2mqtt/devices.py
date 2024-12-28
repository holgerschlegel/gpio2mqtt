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
    Holds device settings specific for the Home Assistant MQTT auto discovery.
    """

    def __init__(self, ha_config: ConfigParser, component_defaults: dict[str, str]):
        """
        Creates an instance from the given device home assistant configuration and the given component defaults.

        Args:
            ha_config (ConfigParser): the device home assistant configuration
            component_defaults (dict[str, str]): the component defaults
        """
        self.enabled: bool = ha_config.get_bool("enabled", default = True)
        self.name: str = ha_config.get_str("name", mandatory = self.enabled)
        if component_defaults:
            for key, default_name in component_defaults.items():
                name_key: str = key + "_name"
                self.__setattr__(name_key, ha_config.get_str(name_key, default = default_name))


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
        self._ha_info: HomeAssistantInfo = HomeAssistantInfo(
                device_config.get_node_parser("homeassistant"), self.get_discovery_component_defaults())

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
        if self._ha_info and self._ha_info.enabled:
            topic: str = self._mqtt.homeassistant_topic + "/device/gpio2mqtt/" + self.id + "/config"
            payload: dict = self.get_discovery_payload()
            _LOGGER.debug("Publishing Home Assistant discovery for %s with id %s: %s",
                    self.__class__.__name__, self.id, payload)
            self._mqtt.publish(topic, payload, retain = True)
        else:
            _LOGGER.debug("Home Assistant discovery disabled for %s with id %s", self.__class__.__name__, self.id)


    def get_discovery_payload(self) -> dict:
        """
        Gets the payload for Home Assistant MQTT auto discovery for this device.

        Returns:
            dict: _description_
        """
        payload: dict = {
            "device" : {
                "identifiers" : self.id,
                "name" : self._ha_info.name,
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


    def get_discovery_component_defaults(self) -> dict[str, str]:
        """
        Gets the defaults for the components for Home Assistant MQTT auto discovery.
        The returned dict musst contain one entry for each component/entity with the component friendly name as value.

        Returns:
            dict[str, str]: the component defaults
        """
        return dict()


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
            **kwargs
    ) -> dict[str, dict]:
        """
        Helper method to get the discovery config for a single component/entity of this device.
        The given component key is used to build the object_id and unique_id values and as key for the component in
        the returned dict. The component name is set to the value from the device config node "homeassistant" using
        the component key plus the suffix "_name".
        This method is meant to be used from get_discovery_components.

        Args:
            platform (str): the entity platform
            component_key (str): the component key
        Returns:
            dict[str, dict]: _description_
        """
        object_id: str = self.id + "_" + component_key
        config: dict = {
            "platform" : platform,
            "object_id" : object_id,
            "unique_id" : object_id,
            "name" : str(getattr(self._ha_info, component_key + "_name", component_key)),
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
                    _LOGGER.debug("Created %s with id %s", device.__class__.__name__, device.id)
        return devices
