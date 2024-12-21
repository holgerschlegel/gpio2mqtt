from abc import abstractmethod
from gpiozero import Device as GpioDevice
from gpiozero.pins.mock import MockFactory
import logging

from .config import ConfigParser
from .mqtt import MqttConnection

_LOGGER = logging.getLogger(__name__)

 
class Device():
    """
    Base class for devices.
    """

    def __init__(self, device_config: ConfigParser, mqtt: MqttConnection):
        """
        Creates an instance from the given device configuration node.

        Args:
            device_config (ConfigParser): the device configuration
            mqtt (MqttConnection): the mqtt connection
        """
        self._id: str = device_config.get_str("id", mandatory = True, regex_pattern = "[a-zA-Z0-9_-]+")
        self._name: str = device_config.get_str("name", mandatory = True)
        self._mqtt = mqtt

        self._state_topic: str = self._mqtt.base_topic + "/" + self.name

    
    def __str__(self):
        return f"Device(id={self._id}, name={self._name})"


    @property
    def id(self) -> str:
        """
        Returns:
            str: the unique device id
        """
        return self._id


    @property
    def name(self) -> str:
        """
        Returns:
            str: the unique device name
        """
        return self._name
    

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
        pass


    @abstractmethod
    def stop(self) -> None:
        """
        Stops the device.
        """
        pass


    @abstractmethod
    def loop(self) -> None:
        """
        Invoked from the main loop. Devices may use it to publish collected the device values to MQTT. 
        """
        pass


    def mock_input(self) -> None:
        """
        Use for testing purpose only. Mocks/simulates an input on the device.
        """
        pass



class Devices:
    """
    Handles the devices.
    """
    
    def __init__(self, device_classes: list[type[Device]], config: ConfigParser, mqtt: MqttConnection):
        """
        Creates an instance.

        Args:
            device_classes (list[type[Device]]): the available device classes, passes as argument to break cyclic imports
            config (ConfigParser): the application configuration
            mqtt (MqttConnection): the mqtt connection
        """
        self._device_classes: dict[str, type[Device]] = { clazz.__name__ : clazz for clazz in device_classes }
        self._devices = self._create_devices(config, mqtt)


    def start(self) -> None:
        """
        Starts the defined devices.
        """
        for device in self._devices:
            device.start()


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
        return isinstance(GpioDevice.pin_factory, MockFactory)


    def mock_input(self) -> None:
        """
        Use for testing purpose only. Mocks/simulates a GPIO input on the first device.
        """
        if self._devices:
            self._devices[0].mock_input()


    def _create_devices(self, config: ConfigParser, mqtt: MqttConnection) -> list[Device]:
        device_configs: list[ConfigParser] = config.get_list_parsers("devices", _LOGGER)
        known_types: set[str] = set(self._device_classes.keys())
        ids: set[str] = set()
        names: set[str] = set()
        devices: list[Device] = []
        for device_config in device_configs:
            type: str = device_config.get_str("type", mandatory = True, allowed = known_types)
            if type is not None:
                device_class = self._device_classes.get(type)
                device = device_class(device_config, mqtt)
                device_config.check_unique("id", device.id, ids)
                device_config.check_unique("name", device.name, names)
                if not device_config.has_errors:
                    devices.append(device)
                    _LOGGER.debug("Created %s with id %s", device.__class__.__name__, device.id)
        return devices
