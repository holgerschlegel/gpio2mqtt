# GPIO2MQTT

A simple project to count Raspberry Pi GPIO input pulses and publish the total count and some derived values via MQTT to Home Assistant.

My first project in Python ...

**This project is at a very early stage and definitely not feature complete ...**


## Todos
- [x] startup, main loop, shutdown (via SIGTERM or ctrl-c)
- [x] yaml config file
- [x] talk to MQTT (using paho.mqtt lib)
- [x] basic pulse counter device that only counts pulses and publishes its state to MQTT
- [x] use gpiozero with rpi-lgpio instead of rpi.gpio
- [x] improve logging config
- [x] add topic/subscription to calibrate/set count value of a pulse counter
- [ ] implement pulse counter based energy meter (Ferraris counter) with enery (kWh) and power (W or kW) output
- [ ] systemd service file and notification integration
- [ ] devices publish home assistant auto discovery message to MQTT


## Bookmarks for References and Docs

- https://github.com/yaleman/mqttgpio
- https://github.com/eclipse-paho/paho.mqtt.python/blob/master/README.rst#network-loop
- https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery
- https://gpiozero.readthedocs.io/en/stable/index.html


## Hardware Setup

Raspberry Pi (3B) connected to the LAN

GPIO pin layout: https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio

TCRT5000 sensor
- 3V3 power (pin 1)
- Ground (pin 9)
- GPIO 17 (pin 11)


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

Create config.yml
- run `.venv/bin/python -m gpio2mqtt --validate` to validate the configuration file without starting the service


## Run without Systemd

From project directory
- `.venv/bin/python -m gpio2mqtt`
