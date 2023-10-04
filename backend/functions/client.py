"""
Contains code dealing with API clients
"""

from typing import Any, Dict, List, Optional, Union

import json

import requests

import time
sleeptime = .2 # 0.01 triggered a "Too many requests" when cleaning the 3rd company

class Client:
    """
    (Example) class for a API client

    Mostly used in the scenario runner
    """

    base_url: str
    """
    The base URL (entry point) of the API server
    """

    default_headers: Dict[str, str]
    """
    The headers to send along with every request
    """

    session: requests.Session
    """
    Requests session to run requests with
    """

    discovery: Optional[Dict[str, str]]
    """
    Discovery dictionary
    """

    def __init__(self, base_url: str, default_headers: Dict[str, str]) -> None:
        self.base_url = base_url

        self.default_headers = default_headers

        self.session = requests.session()

        self.discovery = None

    def check_discovery(self) -> None:
        """
        Checks whether discovery has been run, and, if not, runs it

        A proper client would also expire the discovery after 10 hours
        """
        if self.discovery is not None:
            return

        response = self.session.get(self.base_url, headers=self.default_headers)
        # assert response.ok, response.text
        data = response.json()
        self.discovery = {
            discovery['rel']: discovery['href']
            for discovery in data['data']
        }

    def get(
            self,
            url_name: str,
            query: Optional[Dict[str, List[Any]]] = None,
            **kwargs: str
        ) -> Dict[str, Any]:
        """
        Performs a GET request on the API server, on the URL with the given
        name

        The URL names are found in the discovery
        """
        url = self.get_url(url_name, kwargs)
        response = self.session.get(url, params=query, headers=self.default_headers)
        time.sleep(sleeptime)
        # assert response.ok, response.text
        return response.json() # type: ignore

    def post(
            self,
            url_name: str,
            data: Union[List[Dict[str, Any]], Dict[str, Any]],
            query: Optional[Dict[str, List[Any]]] = None,
            **kwargs: str
        ) -> Dict[str, Any]:
        """
        Performs a POST request on the API server, on the URL with the given
        name

        The URL names are found in the discovery
        """
        url = self.get_url(url_name, kwargs)
        response = self.session.post(
            url, data=json.dumps(data).encode(), params=query, headers=self.default_headers
        )
        time.sleep(sleeptime)
        # assert response.ok, response.text
        return response.json() # type: ignore

    def patch(
            self,
            url_name: str,
            data: Union[List[Dict[str, Any]], Dict[str, Any]],
            **kwargs: str
        ) -> Dict[str, Any]:
        """
        Performs a PATCH request on the API server, on the URL with the given
        name

        The URL names are found in the discovery
        """
        url = self.get_url(url_name, kwargs)
        response = self.session.patch(
            url, data=json.dumps(data).encode(), headers=self.default_headers
        )
        time.sleep(sleeptime)
        # assert response.ok, response.text
        return response.json() # type: ignore

    def delete(
            self,
            url_name: str,
            data: Union[List[Dict[str, Any]], Dict[str, Any]],
            query: Optional[Dict[str, List[Any]]] = None,
            **kwargs: str
        ) -> Dict[str, Any]:
        """
        Performs a DELETE request on the API server, on the URL with the given
        name

        The URL names are found in the discovery
        """
        url = self.get_url(url_name, kwargs)
        response = self.session.delete(
            url, data=json.dumps(data).encode(), params=query, headers=self.default_headers
        )
        time.sleep(sleeptime)
        # assert response.ok, response.text
        return response.json() # type: ignore

    def get_url(self, url_name: str, url_args: Dict[str, str]) -> str:
        """
        Returns an URL by name from the discovery and apply the URL arguments
        """
        self.check_discovery()
        time.sleep(sleeptime)
        assert self.discovery is not None # typehint
        return self.discovery[url_name].format(**url_args)

    def dump(self, what: Any) -> None: # pylint: disable=R0201 # pragma: no cover
        """
        Dumps what as json
        """
        # This is not covered because a) it is only used for testing
        # and b) due to the imports being done in line, we can't use mocking,
        # which would result in us testing the pygments library
        json_str = json.dumps(what, indent=4)

        try:
            # pylint: disable=C0415

            from pygments import highlight # type: ignore
            from pygments.lexers import JsonLexer # type: ignore
            from pygments.formatters import TerminalFormatter # type: ignore

            print(highlight(json_str, JsonLexer(), TerminalFormatter()))
        except ImportError:
            print(json_str)
