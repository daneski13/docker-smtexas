import datetime
import logging
import os
from sqlalchemy import event, DateTime, Numeric, create_engine, Column, Integer, String, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import paho.mqtt.client as mqtt
import pandas as pd

Base = declarative_base()


class Publisher:
    """
    This class is responsible for publishing meter readings to MQTT and/or
    storing them in a database depending on the configuration.
    """

    def __init__(self, interval_enabled: bool = False):
        self.logger = logging.getLogger()

        self.interval_enabled = interval_enabled

        # MQTT settings
        self.mq_host = os.getenv('SMT_MQTT_HOST')
        try:
            self.mq_port = int(os.getenv('SMT_MQTT_PORT', '1883'))
        except ValueError:
            self.logger.error('Invalid MQTT port, defaulting to 1883')
            self.mq_port = 1883
        self.mq_topic = os.getenv('SMT_MQTT_TOPIC', 'smt/meter')

        # DB settings
        self.db_url = os.getenv('SMT_DB_URL')
        self.db_table = os.getenv('SMT_DB_TABLE', 'smt_meter')
        self.db_table_interval = os.getenv(
            'SMT_DB_TABLE_INTERVAL', 'smt_interval')

        # Initialize MQTT and DB
        self.mq_client = self._set_mqtt()
        self.db_session = self._set_db()

    def __del__(self):
        if self.mq_client is not None:
            self.mq_client.disconnect()
            self.mq_client.loop_stop()
        if self.db_session is not None:
            self.db_session.close()

    def publish(self, read_date: datetime.datetime, read_value: float):
        """
        Publish the meter reading to MQTT and save it to the database if configured.
        """
        # MQTT Publish
        if self.mq_client is not None:
            # JSON string to publish
            json_str = f'{{"date": "{read_date.isoformat()}", "value": {
                read_value}}}'
            # Publish to MQTT
            self.mq_client.publish(self.mq_topic, json_str)
        # Database save
        if self.db_session is not None:
            # Save to database
            if hasattr(self, '_meter_table'):
                meter_reading = self._meter_table(
                    date=read_date.replace(tzinfo=None), value=read_value)
                self.db_session.add(meter_reading)
                self.db_session.commit()
            else:
                self.logger.error('Database table not initialized.')

    def save_interval(self, interval_data: pd.DataFrame):
        if not self.interval_enabled or self.db_session is None:
            return
        if not hasattr(self, '_interval_table'):
            self.logger.error('Interval table not initialized.')
            return
        self.logger.info('Saving interval data...')

        db_latest_interval = self.db_session.query(
            func.max(self._interval_table.usage_start_time)).scalar()
        # Check if there is new data to save
        if db_latest_interval is not None:
            # Get the latest interval from the df
            df_latest_interval = interval_data['USAGE_START_TIME'].max()
            if db_latest_interval >= df_latest_interval.tz_localize(None):
                self.logger.info('No new interval data to save')
                return

        # Save the new interval data
        for row in interval_data.itertuples():
            interval_reading = self._interval_table(
                usage_start_time=row.USAGE_START_TIME.tz_localize(None),
                usage_end_time=row.USAGE_END_TIME.tz_localize(None),
                usage_kwh=row.USAGE_KWH,
                estimated_actual=row.ESTIMATED_ACTUAL,
                consumption_surplusgeneration=row.CONSUMPTION_SURPLUSGENERATION
            )
            self.db_session.add(interval_reading)
        self.db_session.commit()

    def _set_mqtt(self):

        def on_connect(client, userdata, flags, rc, properties=None):
            if rc == 0:
                self.logger.info('Connected to MQTT broker')
            else:
                self.logger.error(
                    'Failed to connect to MQTT broker, rc: %s', rc)

        def on_publish(client, userdata, mid):
            self.logger.info('Meter reading published to MQTT broker')

        if self.mq_host:
            mq_client = mqtt.Client()
            mq_client.on_connect = on_connect
            mq_client.on_publish = on_publish
            try:
                mq_client.connect(self.mq_host, self.mq_port, 60)
                mq_client.loop_start()
                return mq_client
            except Exception as e:
                self.logger.error(f'Error connecting to MQTT broker: {e}')
                return None
        else:
            self.logger.info('MQTT host is not set.')
            return None

    def _set_db(self):
        def on_connect(dbapi_connection, connection_record):
            self.logger.info('Connected to database')

        def on_commit(session):
            self.logger.info('Meter data saved to database')

        if self.db_url:
            # Hourly read table
            class _MeterRead(Base):
                __tablename__ = self.db_table
                id = Column(Integer, primary_key=True)
                date = Column(DateTime)
                value = Column(Numeric(10, 3))

            self._meter_table = _MeterRead

            if self.interval_enabled:
                # Interval table
                class _IntervalRead(Base):
                    __tablename__ = self.db_table_interval
                    id = Column(Integer, primary_key=True)
                    usage_start_time = Column(DateTime)
                    usage_end_time = Column(DateTime)
                    usage_kwh = Column(Numeric(6, 3))
                    estimated_actual = Column(String(1))
                    consumption_surplusgeneration = Column(String(18))

                self._interval_table = _IntervalRead

            try:
                engine = create_engine(self.db_url)
                event.listen(engine, 'connect', on_connect)
                Base.metadata.create_all(engine)
                session = sessionmaker(bind=engine)()
                event.listen(session, 'after_commit', on_commit)
                return session
            except Exception as e:
                self.logger.error(f'Error setting up DB session: {e}')
                return None
        else:
            self.logger.info('Database URL is not set.')
            return None
