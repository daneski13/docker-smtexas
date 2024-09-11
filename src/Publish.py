import datetime
import logging
import os
from sqlalchemy import event, DateTime, Numeric, create_engine, Column, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import paho.mqtt.client as mqtt

Base = declarative_base()


class Publisher:
    """
    This class is responsible for publishing meter readings to MQTT and/or
    storing them in a database depending on the configuration.
    """

    def __init__(self):
        self.logger = logging.getLogger()

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
            json_str = f'{{"date": "{read_date.isoformat()}", "value": {read_value}}}'
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
            self.logger.info('Meter reading saved to database')

        if self.db_url:
            class _MeterRead(Base):
                __tablename__ = self.db_table
                id = Column(Integer, primary_key=True)
                date = Column(DateTime)
                value = Column(Numeric)

            self._meter_table = _MeterRead

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
