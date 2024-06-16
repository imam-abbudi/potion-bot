"""HTTP RPC Provider."""
from typing import Tuple, Type, overload
import json
import cloudscraper
import httpx
from solders.rpc.requests import Body
from solders.rpc.responses import RPCResult
import random
from ...exceptions import SolanaRpcException, handle_exceptions
from .base import BaseProvider
from .core import (
    T,
    _after_request_unparsed,
    _BodiesTup,
    _BodiesTup1,
    _BodiesTup2,
    _BodiesTup3,
    _BodiesTup4,
    _BodiesTup5,
    _HTTPProviderCore,
    _parse_raw,
    _parse_raw_batch,
    _RespTup,
    _RespTup1,
    _RespTup2,
    _RespTup3,
    _RespTup4,
    _RespTup5,
    _Tup,
    _Tup1,
    _Tup2,
    _Tup3,
    _Tup4,
    _Tup5,
    _Tuples,
)

proxy_cache = {}
proxy_bool = False


def get_proxies_txt():
    if 'cache' in proxy_cache:
        return proxy_cache['cache']
    with open('proxies.txt', 'r') as file:
        proxies_list = file.read().splitlines()
        proxy_cache['cache'] = proxies_list
        return proxies_list


def get_proxy():
    proxies_list = get_proxies_txt()
    ip, port, user, password = random.choice(proxies_list).split(':')
    text_proxy: dict = {'http://': f"http://{user}:{password}@{ip}:{port}"}
    return text_proxy


class HTTPProvider(BaseProvider, _HTTPProviderCore):
    """HTTP provider to interact with the http rpc endpoint."""

    def __str__(self) -> str:
        """String definition for HTTPProvider."""
        return f"HTTP RPC connection {self.endpoint_uri}"

    @handle_exceptions(SolanaRpcException, httpx.HTTPError)
    def make_request(self, body: Body, parser: Type[T]) -> T:
        """Make an HTTP request to an http rpc endpoint."""
        raw = self.make_request_unparsed(body)
        return _parse_raw(raw, parser=parser)

    def make_request_unparsed(self, body: Body) -> str:
        """Make an async HTTP request to an http rpc endpoint."""
        sesh = cloudscraper.create_scraper()
        request_kwargs = self._before_request(body=body)
        nigga = request_kwargs['content']
        del request_kwargs['content']
        request_kwargs['json'] = json.loads(nigga)
        raw_response = sesh.post(**request_kwargs, proxies=get_proxy() if proxy_bool else None)
        return _after_request_unparsed(raw_response)

    def make_batch_request_unparsed(self, reqs: Tuple[Body, ...]) -> str:
        """Make an async HTTP request to an http rpc endpoint."""
        request_kwargs = self._before_batch_request(reqs)
        raw_response = httpx.post(**request_kwargs)
        return _after_request_unparsed(raw_response)

    @overload
    def make_batch_request(self, reqs: _BodiesTup, parsers: _Tup) -> _RespTup:
        ...

    @overload
    def make_batch_request(self, reqs: _BodiesTup1, parsers: _Tup1) -> _RespTup1:
        ...

    @overload
    def make_batch_request(self, reqs: _BodiesTup2, parsers: _Tup2) -> _RespTup2:
        ...

    @overload
    def make_batch_request(self, reqs: _BodiesTup3, parsers: _Tup3) -> _RespTup3:
        ...

    @overload
    def make_batch_request(self, reqs: _BodiesTup4, parsers: _Tup4) -> _RespTup4:
        ...

    @overload
    def make_batch_request(self, reqs: _BodiesTup5, parsers: _Tup5) -> _RespTup5:
        ...

    def make_batch_request(self, reqs: Tuple[Body, ...], parsers: _Tuples) -> Tuple[RPCResult, ...]:
        """Make a HTTP batch request to an http rpc endpoint.

        Args:
            reqs: A tuple of request objects from ``solders.rpc.requests``.
            parsers: A tuple of response classes from ``solders.rpc.responses``.
                Note: ``parsers`` should line up with ``reqs``.

        Example:
            >>> from solana.rpc.providers.http import HTTPProvider
            >>> from solders.rpc.requests import GetBlockHeight, GetFirstAvailableBlock
            >>> from solders.rpc.responses import GetBlockHeightResp, GetFirstAvailableBlockResp
            >>> provider = HTTPProvider("https://api.devnet.solana.com")
            >>> reqs = (GetBlockHeight(), GetFirstAvailableBlock())
            >>> parsers = (GetBlockHeightResp, GetFirstAvailableBlockResp)
            >>> provider.make_batch_request(reqs, parsers) # doctest: +SKIP
            (GetBlockHeightResp(
                158613909,
            ), GetFirstAvailableBlockResp(
                86753592,
            ))
        """
        raw = self.make_batch_request_unparsed(reqs)
        return _parse_raw_batch(raw, parsers)

    def is_connected(self) -> bool:
        """Health check."""
        try:
            response = httpx.get(self.health_uri)
            response.raise_for_status()
        except (IOError, httpx.HTTPError) as err:
            self.logger.error("Health check failed with error: %s", str(err))
            return False

        return response.status_code == httpx.codes.OK
