from smart_meter_texas import Account, Client, ClientSSLContext, Meter
import logging
import aiohttp
import pytz


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

    async def start(self):
        # Get meter
        async with _SMT_Client_Manager(self.account) as client:
            meters: list[Meter] = await self.account.fetch_meters(client)
            self.meter = meters[0]

    async def read_meter(self):
        timezone = pytz.timezone('America/Chicago')
        self.logger.info('Reading meter...')
        async with _SMT_Client_Manager(self.account) as client:
            await self.meter.read_meter(client)
            date = self.meter.reading_datetime.astimezone(timezone)
            reading = self.meter.reading
            self.logger.info(f'Meter read: {date}, {reading}')
            return date, reading
