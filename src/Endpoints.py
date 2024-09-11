"""
This module contains endpoints for the API.
"""
from abc import ABC
import time
import requests
from enum import Enum
import logging
import datetime

SHARED_HEADERS = {
    'Content-Type': 'application/json',
    'Accept': 'application/json, text/plain, */*',
    'Sec-Fetch-Site': 'same-origin',
    'Accept-Language': 'en-US,en;q=0.9',
    'Sec-Fetch-Mode': 'cors',
    'Origin': 'https://www.smartmetertexas.com',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15',
    'Sec-Fetch-Dest': 'empty',
    'Priority': 'u=3, i',
}


class HttpMethod(Enum):
    GET = 'GET'
    POST = 'POST'
    PUT = 'PUT'
    DELETE = 'DELETE'

    def method(self, session: requests.Session):
        method_map = {
            'GET': session.get,
            'POST': session.post,
            'PUT': session.put,
            'DELETE': session.delete
        }
        return method_map.get(self.value, None)


class Response:
    def __init__(self, response):
        self.status_code = response.status_code
        try:
            self.json = response.json()
        except Exception as e:
            logger = logging.getLogger()
            logger.warning('HTTP response is not JSON')
            logger.debug('%s', e)
        self.text = response.text


class EndpointBase(ABC):
    """
    Base class for all endpoints.

    Attributes:
    url (str): The URL of the endpoint.
    method (HttpMethod): The HTTP method to use.
    headers (dict): Additional headers to use in the request (if any).
    body (dict): The body of the request (if any).
    """

    session = requests.Session()

    @classmethod
    def reset_session(cls):
        cls.session.close()
        cls.session = requests.Session()

    def __init__(self, url: str, method: HttpMethod, headers=None, body=None):
        self.logger = logging.getLogger('smt')
        self.url = url
        self.method = method
        if headers:
            self.headers = {**SHARED_HEADERS.copy(), **headers}
        else:
            self.headers = SHARED_HEADERS
        self.body = body

    def request(self):
        self.logger.debug('REQUEST:\nMethod: %s\nURL: %s\nHeaders: %s\nBody: %s\n',
                          self.method, self.url, self.headers, self.body)
        if self.body:
            response: requests.Response = self.method.method(EndpointBase.session)(
                self.url,
                headers=self.headers,
                json=self.body,
            )
        else:
            response: requests.Response = self.method.method(EndpointBase.session)(
                self.url,
                headers=self.headers,
            )
        rsp = Response(response)
        self.logger.debug('Response: %s %s', rsp.status_code, response.text)
        return rsp


class AuthEndpoint(EndpointBase):
    """
    Endpoint for authenticating with the API.
    """

    def __init__(self, user: str, password: str):
        auth_headers = {
            'Referer': 'https://www.smartmetertexas.com/home',
            'x-amzn-trace-id': f'Service=Authenticate,Request-ID={user}',
        }
        super().__init__(
            'https://www.smartmetertexas.com/commonapi/user/authenticate',
            HttpMethod.POST,
            headers=auth_headers,
            body={
                'username': user,
                'password': password,
                'rememberMe': 'true',
            }
        )

    def authenticate(self) -> str:
        """
        Authenticate with the API and return the Bearer token.
        """
        self.logger.info('Getting auth token...')
        rsp = self.request()
        if rsp.status_code != 200:
            self.logger.critical(
                'FATAL Failed to authenticate. HTTP: %s %s', rsp.status_code, rsp.json)
            exit(1)
        else:
            self.logger.info('Successfully authenticated.')
            return rsp.json.get('token')


class AuthData:
    """
    Data class for the authentication data of token, username, and password.
    """

    def __init__(self, token: str, user: str, password: str):
        self.token = token
        self.user = user
        self.password = password


class AuthenticatedEndpoint(EndpointBase):
    """
    Base class for authenticated endpoints with the exception of the one-time getting of meter info.

    Attributes:
    auth_data (AuthData): The authentication data.
    url (str): The URL of the endpoint.
    method (HttpMethod): The HTTP method to use.
    headers (dict): Additional headers to use in the request (if any), bearer token is automatically added.
    body (dict): The body of the request (if any).
    """

    def __init__(self, auth_data: AuthData, url: str, method: HttpMethod, headers=None, body=None):
        auth_headers = {
            'Authorization': f'Bearer {auth_data.token}',
        }
        if headers:
            headers = {**auth_headers, **headers}
        self.auth_data = auth_data
        super().__init__(url, method, headers, body)

    def refresh(self):
        """
        Refresh the auth token.
        """
        self.logger.info('Refreshing auth token...')
        user, password = self.auth_data.user, self.auth_data.password
        auth_token = AuthEndpoint(user, password).authenticate()
        self.headers['Authorization'] = f'Bearer {auth_token}'
        self.auth_data.token = auth_token
        return self

    def authed_request(self):
        """
        Make an authenticated request, refresh the token if necessary.
        """
        rsp = self.request()
        if rsp.status_code == 401:
            self.logger.warning('Auth token expired, refreshing...')
            self.refresh()
            rsp = self.request()
        return rsp


class DashboardEndpoint(AuthenticatedEndpoint):
    """
    Endpoint for getting the dashboard data. 
    """

    def __init__(self, auth_data: AuthData):
        super().__init__(
            auth_data,
            'https://www.smartmetertexas.com/api/dashboard',
            HttpMethod.POST,
            headers={
                'Referer': 'https://www.smartmetertexas.com/dashboard/',
            }
        )

    def get_numbers(self) -> tuple[str, str]:
        """
        Gets the ESI ID and Meter Number for the user.
        """
        self.logger.info('Getting ESI ID and Meter Number...')
        rsp = self.authed_request()
        if rsp.status_code != 200:
            self.logger.critical(
                'FATAL Failed to get ESI ID and Meter Number')
            exit(1)
        else:
            self.logger.info('Successfully got ESI ID and Meter Number.')
            data = rsp.json.get('data').get('defaultMeterDetails')
            esiid, meter = data.get('esiid'), data.get('meterNumber')
            self.logger.debug('ESIID: %s Meter Number: %s', esiid, meter)
            return esiid, meter


class OnDemandReadEndpoint(AuthenticatedEndpoint):
    """
    This endpoint is used to trigger and on-demand read for the user, to actually fetch the data, use
    LatestReadEndpoint.
    """

    def __init__(self, auth_data: AuthData, esiid: str, meter: str):
        super().__init__(
            auth_data,
            'https://www.smartmetertexas.com/api/ondemandread',
            HttpMethod.POST,
            headers={
                'Referer': 'https://www.smartmetertexas.com/dashboard/',
            },
            body={
                'ESIID': esiid,
                'MeterNumber': meter,
            }
        )

    def trigger_meter_read(self):
        """
        Trigger an on-demand read.

        Warning: This endpoint is a bit buggy on the SMT side which will result in crashing the container.
        To be safe call this endpoint after ensuring a fresh session / re-authentication.
        """
        # Mimic browser behavior by first requesting the dashboard
        DashboardEndpoint(self.auth_data).authed_request()
        # This will rety up to 5 times to trigger the read if the HTTP request fails.
        for _ in range(5):
            self.logger.info('Requesting on-demand meter read...')
            rsp = self.authed_request()
            if rsp.status_code != 200:
                self.logger.warning(
                    'Failed to trigger on-demand read retrying... HTTP: %s %s', rsp.status_code, rsp.text)
                time.sleep(10)
                continue

            try:
                if rsp.json.get('data').get('statusReason') == 'Request submitted successfully for further processing':
                    self.logger.info('On-demand read successfully triggered.')
                    return
                if rsp.json.get('data').get('statusReason') == 'You have reached the limit of two On Demand Read request for this ESIID per hour, you may try again after one hour':
                    self.logger.info('On-demand read already submitted.')
                    return
            except Exception as e:
                self.logger.debug('%s', e)
                self.logger.warning(
                    'Failed to trigger on-demand read retrying... %s', rsp.text)


class LatestReadEndpoint(AuthenticatedEndpoint):
    """
    This endpoint is used to get the latest read data for the user, it will poll until the data is ready.
    """

    def __init__(self, auth_data: AuthData, esiid: str):
        super().__init__(
            auth_data,
            'https://www.smartmetertexas.com/api/usage/latestodrread',
            HttpMethod.POST,
            headers={
                'Referer': 'https://www.smartmetertexas.com/dashboard/',
            },
            body={
                'ESIID': esiid,
            }
        )

    def read_meter(self):
        """
        Get the latest read data. Returns the date and meter value. If none something went wrong.
        """
        self.logger.info('Getting latest read data...')
        # Need to poll until the data is ready, will cap at 45 minutes though to prevent infinite loop just in case
        # Data is ready when odrread is a non-zero value, for some reason the API will return a 0 despite a
        # seccess message in the statusReason sometimes, the website appears to poll every 10 seconds until there's a
        # non-zero value as well.
        count = 0
        while True:
            # Cap polling at ~45 minutes
            if count > 270:
                self.logger.error(
                    'Failed to get the latest meter read. Timed out.')
                return None
            time.sleep(10)
            rsp = self.authed_request()
            count += 1
            if rsp.status_code != 200:
                continue
            # Try to read the data, if it fails, it will wait 10 seconds and try again
            try:
                data = rsp.json.get('data')
                if data.get('odrread') != 0:
                    break
            except Exception as e:
                self.logger.warn('Failed to read meter. Retrying... %s', e)
                self.logger.debug('%s', e)

        date, value = data.get('odrdate'), data.get('odrread')
        date = datetime.datetime.strptime(date, '%m/%d/%Y %H:%M:%S')
        self.logger.info(
            'Meter read data received successfully for Date: %s with Value: %s', date, value)
        return date, float(value)
