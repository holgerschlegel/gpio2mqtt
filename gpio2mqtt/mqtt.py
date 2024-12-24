from collections.abc import Callable
import json
import logging
import paho.mqtt.client as mqtt_client

from .config import ConfigParser

_LOGGER = logging.getLogger(__name__)


MqttConnectionOnMessage = Callable[[mqtt_client.MQTTMessage], None]


class MqttConnection:
    """
    Handles the connection with the MQTT broker.
    """

    def __init__(self, config: ConfigParser):
        """Creates an instance.

        Args:
            config (ConfigParser): the application configuration
        """
        mqtt_config: ConfigParser = config.get_node_parser("mqtt", _LOGGER)
        self._host = mqtt_config.get_str("host", mandatory = True)
        self._port = mqtt_config.get_int("port", mandatory = True, default = 1883, min = 1, max = 65535)
        self._base_topic = mqtt_config.get_str("base_topic", mandatory = True, default = "gpio2mqtt")
        user: str = mqtt_config.get_str("user", mandatory = True)
        password: str = mqtt_config.get_str("password", mandatory = True)
        client_id: str = mqtt_config.get_str("client_id")

        # configure mqtt client but do not connect now
        self._client: mqtt_client.Client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2, client_id)
        self._client.username = user
        self._client.password = password
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        self._message_handlers: dict[str, set[MqttConnectionOnMessage]] = {}
        self._bridge_state_topic: str = self._base_topic + "/bridge/state"
        self._client.will_set(self._bridge_state_topic, self._get_bridge_state_payload_str(False), qos = 0, retain = True)


    @property
    def base_topic(self) -> str:
        """
        Returns:
            str: the gpio2mqqt base topic
        """
        return self._base_topic


    def start(self) -> bool:
        """
        Connects to the MQTT broker and starts the network loop.

        Returns:
            bool: True if successful, False otherwise
        """
        _LOGGER.info("Connecting to MQTT broker %s:%d", self._host, self._port)
        error_code: mqtt_client.MQTTErrorCode = self._client.connect(self._host, self._port)
        result: bool = error_code == mqtt_client.MQTTErrorCode.MQTT_ERR_SUCCESS
        if result:
            self._client.loop_start()
        else:
            _LOGGER.critical("Connection to MQTT broker %s:%d failed: error_code=%s", self.host, self._port, error_code)
        return result


    def stop(self) -> None:
        """
        Stops the network loop and disconnects from the MQTT broker. Does nothing if not connected.
        """
        if self._client.is_connected:
            _LOGGER.info("Disconnecting from MQTT broker")
            self.publish(self._bridge_state_topic, self._get_bridge_state_payload_str(False), as_json = False, retain = True)
            self._client.loop_stop()
            error_code: mqtt_client.MQTTErrorCode = self._client.disconnect()


    def publish(self, topic: str, payload: any, as_json: bool = True, qos: int = 0, retain: bool = False) -> bool:
        """
        Publishes the given payload to the given topic.

        Args:
            topic (str): the topic (absolute, including the base topic)
            payload (any): the message to send
            as_json (bool): True to serialize the given payload as json before publish, False to publish the payload as-is
            qos (int, optional): the quality of service level
            retain (bool, optional): True to send a retained message, False otherwise
        Returns:
            bool: True if successful, False otherwise
        """
        _LOGGER.debug("Publishing message to %s: %s", topic, payload)
        if as_json:
            payload = json.dumps(payload)
        info: mqtt_client.MQTTMessageInfo = self._client.publish(topic, payload, qos = qos, retain = retain)
        return info.rc == mqtt_client.MQTTErrorCode.MQTT_ERR_SUCCESS


    def add_message_handler(self, topic: str, handler: MqttConnectionOnMessage) -> None:
        """
        Adds the given handler for messages of the given topic.

        Args:
            topic (str): the topic to subscribe
            handler (MqttConnectionOnMessage): the on message handler callback
        """
        handlers = self._message_handlers.get(topic)
        if handlers is None:
            handlers = { handler }
            self._message_handlers[topic] = handlers
            if self._client.is_connected:
                _LOGGER.info("Subscribing to topic %s", topic)
                self._client.subscribe(topic)
        else:
            handlers.add(handler)


    def remove_message_handler(self, topic: str, handler: MqttConnectionOnMessage) -> None:
        """
        Removes the given handler for messages of the given topic. Does nothing if the given handler is unknown.

        Args:
            topic (str): the topic to subscribe
            handler (MqttConnectionOnMessage): the on message handler callback
        """
        handlers = self._message_handlers.get(topic)
        if handlers:
            handlers.discard(handler)
            if not handlers and self._client.is_connected:
                _LOGGER.info("Unsubscribing from topic %s", topic)
                # unsubscribe after removing last handler for a topic
                self._client.unsubscribe(topic)


    def _get_bridge_state_payload_str(self, online: bool) -> str:
        payload: dict = { "state" : "online" if online else "offline" }
        return json.dumps(payload)


    def _on_connect(self, client: mqtt_client.Client, userdata, connect_flags, reason_code, properties):
        _LOGGER.debug("Connected with reason code %s", reason_code)
        self.publish(self._bridge_state_topic, self._get_bridge_state_payload_str(True), as_json = False, retain = True)
        # (re)subscribe to topics with added handlers
        for topic in self._message_handlers.keys():
            _LOGGER.info("Subscribing to topic %s", topic)
            self._client.subscribe(topic)


    def _on_disconnect(self, client: mqtt_client.Client, userdata, disconnect_flags, reason_code, properties):
        _LOGGER.debug("Disconnected with reason code %s", reason_code)


    def _on_message(self, client: mqtt_client.Client, userdata, message: mqtt_client.MQTTMessage):
        _LOGGER.debug("Received message on topic %s: %s", message.topic, str(message.payload))
        handlers = self._message_handlers.get(message.topic)
        if handlers:
            # iterate over copy to allow that handlers remove subscriptions
            for handler in handlers.copy():
                handler(message)
