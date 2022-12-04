import requests
from aiohttp import ClientSession, ClientResponse
from bs4 import BeautifulSoup

BASE_URL = "https://www.unitedconsumers.com/mijn-unitedconsumers"
LOGIN_URL = BASE_URL + "/account/log-in.asp"
TARIF_URL1 = BASE_URL + "/mijn-energie/tarieven/index.asp"
TARIF_URL2 = BASE_URL + "/mijn-energie/tarieven/tarieven.asp"


class UnitedConsumers:
    """Class to interact with Mijn United Consumers."""

    _session: ClientSession
    _username: str
    _password: str

    def __init__(self, websession: ClientSession) -> None:
        """Initialize."""
        self._session = websession

    async def authenticate(self, username: str, password: str) -> bool:
        """Authenticate to mijn united consumers."""
        resp = await self._session.post(
            LOGIN_URL,
            data={
                "username": username,
                "password": password,
                "login": "Inloggen",
            },
            allow_redirects=False,
        )

        if resp.status == 302:
            # We are redirected to the dashboard, so credentials are correct.
            self._username = username
            self._password = password
            return True

        # Code 200 means we are back at the login and thus credentials are not correct.
        # Anything else is also not expected.
        return False

    async def _reauth(self):
        return await self.authenticate(self._username, self._password)

    async def _get(self, url: str):
        resp = await self._session.get(url)

        if resp.status == 301:
            # we are redirected to the login page.
            # Try to reauthenthicate and fetch again.
            if await self._reauth():
                resp = await self._session.get(url)
            else:
                raise UcAuthError("Failed to reauthenticate using stored credentials.")

        return resp

    # TODO: Make more DRY
    async def _post(self, url: str, data: dict):
        resp = await self._session.post(url, data=data)

        if str(resp.url) == LOGIN_URL:
            # we are redirected to the login page.
            # Try to reauthenthicate and fetch again.
            if await self._reauth():
                resp = await self._session.get(url, data=data)
            else:
                raise UcAuthError("Failed to reauthenticate using stored credentials.")

        return resp

    async def _get_price_form_data(self) -> dict:
        resp = await self._get(TARIF_URL1)
        text = await resp.text()
        soup = BeautifulSoup(text, "html.parser")
        form_inputs = soup.find(id="formAdres").find_all("input")

        data = {}
        for form_input in form_inputs:
            data[form_input["name"]] = form_input["value"]

        return data

    async def _get_price_data(self) -> dict:
        data = await self._get_price_form_data()
        resp = await self._post(TARIF_URL2, data)
        text = await resp.text()
        soup = BeautifulSoup(text, "html.parser")

        rows = []
        for current in soup.find_all("div", class_="current"):
            rows += current.find_all("div", class_="row", recursive=False)

        return_data = {}
        for row in rows:
            cells = row.find_all("div")
            name = cells[0].get_text()
            if expandable := cells[-1].find("a"):
                value = expandable.get_text()
            else:
                value = cells[-1].get_text()

            value = value.strip("\r\n\t€ ").replace(",", ".")

            try:
                value = float(value)
            except ValueError:
                continue

            if name == "Normaaltarief (per kWh)":
                return_data["high"] = value
            elif name == "Daltarief (per kWh)":
                return_data["low"] = value
            elif name == "Teruglevertarief normaal (per kWh)":
                return_data["ret-high"] = value
            elif name == "Teruglevertarief dal (per kWh)":
                return_data["ret-low"] = value
            elif name == "Gastarief (per m3)":
                return_data["gas"] = value

        return return_data

    async def fetch_data(self) -> dict:
        """Fetch all data from United Consumers."""
        return self._get_price_data()


class UcError(Exception):
    """Base exception of United Consumers library."""


class UcAuthError(UcError):
    """An attempt to authenticate failed."""
