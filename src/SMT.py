from smart_meter_texas import Account, Client, ClientSSLContext, Meter
import logging
import aiohttp
import pytz
import datetime as dt


class _SMT_Client_Manager:
    """
    Little helper class to manage the client session and client object
    from the SMT library.
    """

    def __init__(self, acc: Account):
        self.account = acc

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        ssl_clt = ClientSSLContext()
        ssl_ctx = await ssl_clt.get_ssl_context()

        if ssl_ctx is None:
            raise Exception('Failed to create SSL context')
        self.client = Client(self.session,
                             self.account, ssl_ctx)
        return self.client

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.session.close()


class SMT:
    def __init__(self, user: str, password: str):
        self.logger = logging.getLogger()
        self.account = Account(user, password)
        self.timezone = pytz.timezone('America/Chicago')

    async def start(self):
        # Get meter
        async with _SMT_Client_Manager(self.account) as client:
            meters: list[Meter] = await self.account.fetch_meters(client)
            self.meter = meters[0]

    async def read_meter(self):
        self.logger.info('Reading meter...')
        async with _SMT_Client_Manager(self.account) as client:
            await self.meter.read_meter(client)
            date = self.meter.reading_datetime.astimezone(self.timezone)
            reading = self.meter.reading
            self.logger.info(f'Meter read: {date}, {reading}')
            return date, reading

    async def read_interval(self, now: dt.datetime, start=None):
        self.logger.info('Reading interval data...')
        yesterday = now - dt.timedelta(days=1)
        try:
            async with _SMT_Client_Manager(self.account) as client:
                if start:
                    await self.meter.get_interval(client, start, now)
                # Try to get interval data for the prior day
                await self.meter.get_interval(client, yesterday, yesterday)
                df = self.meter.read_interval
                df["USAGE_START_TIME"] = df["USAGE_START_TIME"].dt.tz_convert(
                    self.timezone)
                df["USAGE_END_TIME"] = df["USAGE_END_TIME"].dt.tz_convert(
                    self.timezone)
                return df
        except Exception as e:
            self.logger.warning('Could not get the prior day interval data')
            self.logger.debug(str(e))
            raise e
