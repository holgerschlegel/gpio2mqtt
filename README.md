# GPIO2MQTT

A simple project to count Raspberry Pi GPIO input pulses and publish the total count and some derived values via MQTT to Home Assistant.

My first project in Python ...

**This project is at a very early stage and definitely not feature complete ...**


## Features

- Multiple devices/sensors in one program instance
- Publish device values to MQTT state topic
- Listens to device command topics to set device values
- On program start, last published device values can be read from MQTT state topic
- Plain text configuration file
- PulseCounter: a basic pulse counter
- ElectricityPulseMeter: a pulse counter based energy meter (Ferraris counter) with enery (kWh) and power (W) output


## Todos
- systemd service file and notification integration
- devices publish home assistant auto discovery message to MQTT


## Bookmarks for References and Docs

- https://github.com/yaleman/mqttgpio
- https://github.com/flyte/mqtt-io
- https://github.com/eclipse-paho/paho.mqtt.python/blob/master/README.rst#network-loop
- https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery
- https://gpiozero.readthedocs.io/en/stable/index.html


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
- validate configuration with `.venv/bin/python -m gpio2mqtt --validate`


## Configuration File

The configuration file `config.yaml` is loaded from the current working directory.

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
  Client id to use. It not provided, a default client id is generated based on the configured base topic. This default prevents running multiple instances using with the same base topic to prevent problems.
- `base_topic` *default `gpio2mqtt`*  
  Base topic to publish device states.

### devices

A list of devices with the following keys:

- `id` *required*  
  Unique id of the device. Also used to in MQTT topic names for the device.  
  An id must contain only ascii letters (upper, lower), digits, hyphen and underscore.  
- `name` *required*  
  Unique friendly name of the device.
- `type` *required*  
  Device type. The following types are supported:
  - `PulseCounter`  
    Counts high or low input pulses. Publishes a total count and delta values in intervals.  
    Required keys: `gpio_pin`, `active_high`  
    Optional keys: `init_mode`, `publish_interval_seconds`
  - `ElectricityPulseMeter`  
    Pulse counter based electricity meter. Calculates power and energy from counted pulses.  
    Required keys: `gpio_pin`, `active_high`, `pulses_per_kwh`  
    Optional keys: `init_mode`, `publish_interval_seconds`
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


## Run from Shell

From project directory
- `.venv/bin/python -m gpio2mqtt`

Available command line arguments:
- `--logconsole` log to console instead of file
- `--logdebug` additionally log debug information
- `--validate` validate config.yaml and exit
- `--version` show program version and exit
- `--help` show command line help and exit
