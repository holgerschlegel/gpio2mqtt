# GPIO2MQTT

A simple project to count Raspberry Pi GPIO input pulses and publish the total count and some derived values via MQTT to Home Assistant.

My first project in Python ...


## Features

- Multiple devices/sensors in one program instance
- Publish device values to MQTT state topic
- Listens to device command topics to set device values
- On program start, last published device values can be read from MQTT state topic
- Plain text configuration file
- PulseCounter: a basic pulse counter
- ElectricityPulseMeter: a pulse counter based energy meter (Ferraris counter) with enery (kWh) and power (W) output
- Announce devices to Home Assistant MQTT auto discovery
- Systemd service file example and sd_notify integration


## Todos

Nothing left that I have thought of so far ...


## Bookmarks for References and Docs

- https://github.com/flyte/mqtt-io
- https://github.com/eclipse-paho/paho.mqtt.python/blob/master/README.rst#network-loop
- https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery
- https://gpiozero.readthedocs.io/en/stable/index.html
- https://github.com/torfsen/python-systemd-tutorial


## Hardware Setup

Raspberry Pi (3B) connected to the LAN

GPIO pin layout: https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio

TCRT5000 sensor
- 3V3 power (pin 1)
- Ground (pin 9)
- GPIO (BCM 17, pin 11)


## Software Setup

Install git and python3-dev 3.11+ and python3-virtuelenv module

Clone git repository
- `git clone https://github.com/holgerschlegel/gpio2mqtt.git`

Change into project directory
- `cd gpio2mqtt`

Create python virtual environment
- `python -m venv .venv`
- `source .venv/bin/activate`
- `pip install -r requirements.txt`

Create configuration file
- create file `config.yaml`
- validate configuration with `.venv/bin/python -m gpio2mqtt --logconsole --validate`


## Configuration File

The configuration file `config.yaml` is loaded from the current working directory.
An example configuration files is provided as `config.example.yaml`.

### mqtt

- `host` *required*  
  Host name or ip address of the MQTT broker.
- `port` *default `1883`*  
  Port number of the MQTT broker.
- `user` *required*  
  Username to use.
- `password` *required*  
  Password to use.
- `client_id`  
  Client id to use. It not provided, a default client id is generated based on the configured base topic.  
  This default prevents running multiple instances using with the same base topic to prevent problems.
- `base_topic` *default `gpio2mqtt`*  
  Base topic for device state topics. Also used as <node_id> for Home Assistant MQTT auto discovery topics.  
  Can be used to fully separate multiple installations (like dev and prod).
- `homeassistant_topic` *default `homeassistant`*  
  Base topic for Home Assistant MQTT auto discovery.

### devices

A list of devices with the following keys:

- `id` *required*  
  Unique id of the device. Also used to in MQTT topic names for the device.  
  An id must contain only ascii letters (upper, lower), digits, hyphen and underscore.  
- `type` *required*  
  Device type. The following types are supported:
  - `PulseCounter`  
    Counts high or low input pulses. Publishes a total count in intervals.  
    Required keys: `gpio_pin`, `active_high`  
    Optional keys: `init_mode`, `publish_interval_seconds`  
    HA Components: `count`, `timestamp`
  - `ElectricityPulseMeter`  
    Pulse counter based electricity meter. Calculates power and energy from counted pulses.  
    Required keys: `gpio_pin`, `active_high`, `pulses_per_kwh`  
    Optional keys: `init_mode`, `publish_interval_seconds`  
    HA Components: `count`, `timestamp`, `energy`, `power`
- `gpio_pin` *see device types*  
  GPIO pin (BCM) to use.  
- `active_high` *see device types*  
  Whenever to count high or low pulses.  
  `true` to handle high input as active (raising edge).  
  `false` to handle low input as active (falling edge).
- `init_mode` *see device types*  
  How to initialize the last state on program start.  
  `new` (default) to start with zero.  
  `mqtt` to fetch last state from mqtt state topic.
- `publish_interval_seconds` *see device types*  
  Minimum interval in seconds to publish the device state. Independent of this setting, the state is only published if input has been recevied since the last publish.
- `pulses_per_kwh` *see device types*  
  Number if input pulses per 1 kWh.

### device.homeassistant

Information for the Home Assistant MQTT auto discovery.
For each device component (see above), a corresponding `<component>_name` can be set.

- `enabled` *default true*  
  Whenever to announce the device to Home Assistant via MQTT auto discovery message.
- `name` *required if enabled is true*  
  Friendly name for the Home Assistant device.
- `count_name` *default `Count`*  
  Friendly name for the Home Assistant count sensor.
- `timestamp_name` *default `Timestamp`*  
  Friendly name for the Home Assistant timestamp sensor.
- `energy_name` *default `Energy`*  
  Friendly name for the Home Assistant energy sensor.
- `power_name` *default `Power`*  
  Friendly name for the Home Assistant power sensor.


## Run from Shell

From project directory
- `.venv/bin/python -m gpio2mqtt`

Available command line arguments:
- `--logconsole` log to console instead of file
- `--logdebug` additionally log debug information
- `--validate` validate config.yaml and exit
- `--version` show program version and exit
- `--help` show command line help and exit


## Run via Systemd

Create serviced service unit file by copying `gpio2mqtt.example.service` as `gpio2mqtt.service` and edit it to fill in
the placeholders (working directory and user) it contains.

Create a soft link in `/etc/systemd/system` to the created service unit file.
- `sudo ln -s <gpio2mqtt directory>/gpio2mqtt.service /etc/systemd/system/gpio2mqtt.service`

Reload the systemd daemon, enable and start the service:
- `sudo systemctl daemon-reload`
- `sudo systemctl enable gpio2mqtt.service`
- `sudo systemctl start gpio2mqtt.service`
