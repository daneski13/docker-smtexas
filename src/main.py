import os
from datetime import datetime, timedelta
import time
import asyncio
import logging
from SMT import SMT
import Publish as pb


def setup_logger():
    # Set up logging
    log_level = os.getenv('SMT_LOG_LEVEL', 'INFO')
    log_level_valid = True
    if log_level not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
        log_level_valid = False
        log_level = 'INFO'
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    if not log_level_valid:
        logging.getLogger().warning(
            f'Invalid log level "{log_level}", defaulting to INFO')
    return logging.getLogger()


async def main():
    logger = setup_logger()

    logger.info('Starting the SMT client...')
    # Get the SMT username and password from the environment
    user = os.getenv('SMT_USER', None)
    password = os.getenv('SMT_PASSWORD', None)

    # Ensure that the user and password are set
    if user is None or password is None:
        logger.critical(
            'FATAL SMT_USER and SMT_PASSWORD must be set in the environment')
        exit(1)

    # Create the SMT client
    smt = SMT(user, password)
    try:
        await smt.start()
    except Exception as e:
        logger.error('Failed log in to SMT')
        logger.error(str(e))
        exit(1)

    # See if interval data is enabled
    interval_enabled = os.getenv('SMT_INTERVAL_ENABLED', False)
    try:
        interval_enabled = bool(interval_enabled)
        if interval_enabled:
            logger.info('Interval data collection enabled')
    except ValueError:
        interval_enabled = False
        logger.warning(
            'Invalid SMT_INTERVAL_ENABLED value, must be 0 or 1. Defaulting to 0 (disabled)')

    # Create the publisher
    publisher = pb.Publisher(interval_enabled)

    async def read_meter():
        try:
            # Read the meter
            read_date, read_value = await smt.read_meter()
        except Exception as e:
            logger.error('Failed to read meter')
            logger.debug(str(e))
            return
        # Publish the meter reading
        publisher.publish(read_date, read_value)

    # Start the infinite loop
    while True:
        now = datetime.now()
        # Read on the hour
        if now.minute == 0:
            await read_meter()
            # Every 2nd hour, grab 15 minute interval data
            if interval_enabled and now.hour % 2 == 0:
                try:
                    df = await smt.read_interval(now)
                    publisher.save_interval(df)
                except Exception as e:
                    logger.error('Failed to read interval data.')
                    logger.debug(str(e))
            time.sleep(60)  # Sleep for a minute to avoid reading twice
        # Sleep until just before the next hour
        else:
            # Sleep for a bit to stop the loop from running too fast, increasing CPU usage
            time.sleep(0.1)
            next_hour = (now + timedelta(hours=1)).replace(minute=0,
                                                           second=0, microsecond=0)
            delta_seconds = (next_hour - now).total_seconds()
            # If the next hour is more than ~3 minutes away, we're going to sleep
            # otherwise we'll just loop
            if delta_seconds > 170:
                sleep_time = delta_seconds - 120
                logger.info(
                    f'Sleeping until {now + timedelta(seconds=sleep_time)}')
                time.sleep(sleep_time)
            else:
                continue


asyncio.run(main())
