# Docker Smart Meter Texas

This is a very simple and lightweight container that does 1 thing:
retrieves meter reads from the Smart Meter Texas API every hour,
on the hour. These reads are published to an MQTT broker and/or written
to an external SQL database.

<!-- omit in toc -->
## Table of Contents

- [Disclaimer](#disclaimer)
- [Requirements](#requirements)
- [Usage](#usage)
  - [MQTT Publisher](#mqtt-publisher)
    - [Home Assistant](#home-assistant)
  - [Database Integration](#database-integration)
- [Environment Variables](#environment-variables)
  - [Required](#required)
  - [MQTT](#mqtt)
  - [Database](#database)
  - [Additional](#additional)
- [Credits](#credits)

## Disclaimer

This project is not affiliated with nor endorsed by Smart Meter Texas or any affiliated entities. This project interacts with the unofficial Smart Meter Texas (SMT) API. Please note that this API is not officially supported or endorsed by Smart Meter Texas nor any affiliated entities and may be subject to changes, disruptions, or discontinuation without notice. The developer of this project, SMT, nor any affiliated entities are responsible for any issues, disruptions, or inaccuracies that may arise from the use of this software.

By using this software, you acknowledge and accept that the data retrieved from this resource is unofficial and may not be fully accurate or reliable.

## Requirements

- Docker
- An account on [Smart Meter Texas](https://www.smartmetertexas.com/) (login username and password)
- An MQTT broker such as [Mosquitto](https://mosquitto.org/) (optional)*
- A Database instance (optional)*

*An MQTT broker or a database is needed to receive data from this container. To use your electricity meter as a "sensor" such as in Home Assistant, you would likely be using an MQTT broker. For long term storage and analysis, you would likely be using a database. You can use both, or just one depending on your needs. See the [example docker compose file](./docker-compose-example.yml) for an example of how to configure both.

## Usage

See [docker-compose.yml](./docker-compose.yml) for full configuration options and [docker-compose-example.yml](./docker-compose-example.yml) for an example configuration with both MQTT and a database. The [environment variables](#environment-variables) section below explains the configuration options.

### MQTT Publisher

> [!NOTE]
> Currently, MQTT authentication is not supported.

If you have set the `SMT_MQTT_HOST` environment variable, the container will publish meter reads to the specified MQTT broker under the topic specified by `SMT_MQTT_TOPIC` (default: `smt/meter`). The payload will be in JSON format and look something like:

```json
{
  "date": "2024-09-01T00:00:00-05:00",
  "value": 12345.678
}
```

i.e. at 12:00 AM on September 1st, 2024 (US Central Time), the meter was at 12345.678 kWh.

Where `date` is the timestamp of the meter read in ISO 8601 format and `value` is the read value in kWh from the meter.

#### Home Assistant

To use this data in Home Assistant, you can use the [MQTT Sensor](https://www.home-assistant.io/integrations/mqtt/) integration. If you are using HA OS or Supervised you can set up an MQTT broker directly in Home Assistant, see the [Mosquitto add-on](https://github.com/home-assistant/addons/blob/master/mosquitto/DOCS.md). Otherwise, you can use an external MQTT broker such as [Mosquitto's docker container](https://hub.docker.com/_/eclipse-mosquitto). I will not go into detail on how to set up an MQTT broker here.

Here's an example for configuring this sensor in Home Assistant's `configuration.yaml`:

```yaml
mqtt:
  sensor:
    name: SMT Meter
    state_topic: "smt/meter"
    unit_of_measurement: "kWh"
    device_class: energy
    state_class: total_increasing
    value_template: "{{ value_json.value }}"
    unique_id: smt_electricity_meter
```

### Database Integration

If you have configured the `SMT_DB_URL` env variable, the container will write meter reads to a table with a schema something like:

```sql
CREATE TABLE smt_meter (
    id INT AUTO_INCREMENT PRIMARY KEY,
    `date` DATETIME,
    value DECIMAL(10, 3)
);
```

Exact schema may vary depending on the database you're using and by extension the specific SQLAlchemy driver. The table will be created if it doesn't already exist.

If you changed the `SMT_DB_TABLE` environment variable, a table will be created and used with that name instead.

`date` is the timestamp of the meter read and `value` is the read value in kWh from the meter. A `SELECT` will return something like:

| id  | date                | value     |
| --- | ------------------- | --------- |
| 1   | 2024-09-01 00:00:00 | 12345.678 |

i.e. at 12:00 AM on September 1st, 2024, the meter was at 12345.678 kWh.

> [!NOTE]
> Date values written to the database are not timezone-aware; the time is recorded as provided by Smart Meter Texas in US Central Time.

## Environment Variables

### Required

- `SMT_USER` - Smart Meter Texas username
- `SMT_PASSWORD` - Smart Meter Texas password

### MQTT

Required:

- `SMT_MQTT_HOST` - Host/IP of the MQTT broker, setting this will enable MQTT publishing

Optional:

- `SMT_MQTT_PORT` (default: `1883`) - Port of the MQTT broker 
- `SMT_MQTT_TOPIC` (default: `smt/meter`) - Topic to publish meter reads to

### Database

This container uses SQLAlchemy under the hood to save meter reads to an external SQL database. Currently Postgres, MySQL, and MariaDB are supported out of the box. If you need to use a different database, you may need add the appropriate driver to `requirements.txt` and build the container yourself.

Required:

- `SMT_DB_URL` - DB connection URL, setting this will enable writing to a database (e.g. `postgresql://user:password@host:port/dbname`)

Optional:

- `SMT_DB_TABLE` (default: `smt_meter`) - Name of the table to write meter reads to, this table will be created if it doesn't exist


### Additional

- `SMT_LOG_LEVEL` (default: `INFO`) - Log level for the docker container
  - `NOTSET` - No logging
  - `DEBUG` - Debug logging (verbose)
  - `INFO` - Informational logging
  - `WARNING` - Warnings
  - `ERROR` - Errors
  - `CRITICAL` - Critical errors, e.g. the application is about to crash

## Credits

- [Smart Meter Texas Python Package](https://github.com/grahamwetzler/smart-meter-texas) by [Graham Wetzler](https://github.com/grahamwetzler) for the unofficial SMT API wrapper