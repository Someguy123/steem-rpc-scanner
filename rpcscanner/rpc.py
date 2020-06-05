import asyncio
import json
import logging
import time
from collections import namedtuple

import httpx
from typing import Union, Tuple, Iterable, Mapping, Optional
from colorama import Fore
from privex.helpers import empty

from rpcscanner.exceptions import ServerDead, RPCError, RPCMethodNotSupported, RPCInvalidArguments, RPCInvalidArgumentType
from rpcscanner.settings import MAX_TRIES, RPC_TIMEOUT, RETRY_DELAY

log = logging.getLogger(__name__)
# s = AsyncSession(n=50)

RPCBenchResult = namedtuple('RPCBenchResult', 'result time_taken tries', defaults=(0, 0))

RPCBenchType = Union[Tuple[Union[list, dict, str], Union[float, int], int], RPCBenchResult]
"""Combines the :class:`.RPCBenchResult` type with a generic typed :class:`.Tuple` for better IDE handling"""


async def rpc(host: str, method: str, params: Union[dict, list] = None) -> RPCBenchType:
    """
    Handles an RPC request, with automatic re-trying
    and timing.
    :returns: tuple (response, time_taken_sec, tries)
    :raises: ServerDead - tried too many times and failed
    """
    params = [] if params is None else params
    log.debug(f'{Fore.BLUE}Attempting method {method} on server {host}. Will try {MAX_TRIES} times{Fore.RESET}')
    np = NodePlug()
    try:
        d = await np.try_node(host, method, params)
    except ServerDead as e:
        log.debug('caught in rpc and raised')
        raise e

    return d


async def identify_node(host) -> RPCBenchType:
    """
    Detects a server type
    :returns: tuple (servtype, time_taken_sec, tries)
    :raises: ServerDead - tried too many times and failed
    """
    # tries = 0
    log.info('Identifying %s', host)
    log.debug(f'{Fore.BLUE}Attempting method identify_node on server {host}. Will try {MAX_TRIES} times{Fore.RESET}')
    # d = defer.Deferred()
    np = NodePlug()
    try:
        d = await np.ident_jussi(host)
        log.debug('Successfully identified %s', host)
    except ServerDead as e:
        log.debug('caught in identify_node and raised')
        raise e

    # return tuple(results)
    return d


def handle_graphene_err(data: Union[dict, str], method="UNKNOWN", host: str = None, res: httpx.Response = None, **kwargs):
    check_result: bool = kwargs.get('check_result', True)
    status_code = kwargs.get('status_code', res.status_code if not empty(res) else None)

    if isinstance(data, str):
        try:
            data = json.loads(data)
            log.debug("Successfully decoded 'data' from JSON string. Data contents: %s", data)
        except json.JSONDecodeError as e:
            log.warning("Response data is a string but not JSON. Failed to decode to extract errors. %s %s", type(e), str(e))
            log.debug("Dumping string data into 'dict(error=dict(message=DATA))'. Data is:", data)
            data = {"error": {"message": data}}
            log.debug("Converted dict data is:", data)
    else:
        # Clone the dict object to avoid mutating the original one passed to this function.
        data = dict(data)
    
    if 'error' in data:
        err = data.get('error', {})
        msg, code = err.get('message', ''), err.get('code', 0)
        if 'method not found' in msg.lower():
            raise RPCMethodNotSupported(
                f"RPC Method '{method}' not supported", error_msg=msg, error_code=code, response=data, http_status=status_code, host=host
            )
        if 'invalid parameters' in msg.lower() or 'expected #s argument' in msg.lower() or "assert exception:args.size()" in msg.lower():
            raise RPCInvalidArguments(
                f"Invalid arguments passed to RPC Method '{method}' (not enough / too many arguments or wrong types)",
                error_msg=msg, error_code=code, response=data, http_status=status_code, host=host
            )
        if 'invalid cast from' in msg.lower() or 'bad cast:' in msg.lower():
            raise RPCInvalidArgumentType(
                f"Incorrect argument type(s) passed to '{method}'. Method may expect array/nested array/int/string etc.",
                error_msg=msg, error_code=code, response=data, http_status=status_code, host=host
            )
        
        raise RPCError(f"Error while querying '{method}'",
                       host=host, error_msg=msg, error_code=code, response=data, http_status=status_code)
    if check_result and 'result' not in data:
        raise RPCError(
            f"No result while querying '{method}' - and no error could be extracted from the result.",
            response=data, http_status=status_code, host=host
        )
    return None


async def _rpc(host: str, method: str, params=None) -> Union[dict, list, str, int, float]:
    params = [] if params is None else params
    headers = {
        'content-type': 'application/x-www-form-urlencoded'
    }
    payload = {
        "method": method,
        "params": params,
        "jsonrpc": "2.0",
        "id": 1,
    }
    # s.mount(host, HTTPAdapter(max_retries=1))
    async with httpx.AsyncClient() as s:
        res = await s.post(host, data=json.dumps(payload), headers=headers, timeout=RPC_TIMEOUT)
        res.raise_for_status()
        # print(res.text[0:10])
        j = res.json()
        res.close()
        await s.aclose()
    
    # Pass decoded result data to handle_graphene_error, which will raise RPCError or another RPCError-based exception
    # if the RPC node returned a response containing an error message, or the 'result' key is missing.
    handle_graphene_err(j, method=method, host=host, res=res)

    return j['result']


class NodePlug:
    def __init__(self):
        self.last_exception = None
        pass
    
    async def try_node(self, host, method, params=None) -> RPCBenchType:
        params = [] if params is None else params
        try:
            tn = await self._try_node(host, method, params)
            return tn
        except Exception as e:
            log.debug('caught in try_node and raised')
            raise e

    async def _try_node(self, host, method, params: Union[dict, list] = None, tries=0) -> RPCBenchType:
        params = [] if params is None else params
        if tries >= MAX_TRIES:
            log.debug('SERVER IS DEAD')
            raise ServerDead(
                f'{host} did not respond properly after {tries} tries', orig_ex=self.last_exception, host=host
            )

        try:
            log.debug('{} {} attempt {}'.format(host, method, tries))
            start = time.time()
            tries += 1
            res = await _rpc(host, method, params)

            end = time.time()
            runtime = end - start

            # if we made it this far, we're fine :)
            results = RPCBenchResult(result=res, time_taken=runtime, tries=tries)
            log.debug(f'{Fore.GREEN}[{host}] Successful request for {method}{Fore.RESET}')
            return results
        except Exception as e:
            self.last_exception = e
            if 'HTTPError' in str(type(e)) and '426 Client Error' in str(e):
                raise ServerDead(f'Server {host} only supports websockets')
            log.info('%s [%s] %s attempt %d failed. Message: %s %s %s', Fore.RED, method, host, tries, type(e), str(e), Fore.RESET)
            await asyncio.sleep(RETRY_DELAY)
            return await self._try_node(host, method=method, params=params, tries=tries)

    async def ident_jussi(self, host) -> RPCBenchType:
        try:
            tn = await self._ident_jussi(host)
            return tn
        except Exception as e:
            log.debug('caught in ident_jussi and raised')
            raise e
    
    @staticmethod
    def _ident_response(res: Union[str, dict]) -> Optional[str]:
        j = {}
        if isinstance(res, str):
            try:
                j = json.loads(str(res))
            except json.JSONDecodeError:
                j = {}
        if isinstance(res, dict):
            j = dict(res)
            res = json.dumps(j)

        if 'error' in j and 'message' in j['error']:
            if j['error']['message'] == 'End Of File:stringstream':
                return 'appbase'
        if 'jussi_num' in j: return 'jussi'
        if 'end of file:stringstream' in res.lower(): return 'appbase'
        if 'could not call api' in res.lower(): return 'legacy'
        return None

    async def _ident_jussi(self, host, tries=0):
        if tries >= MAX_TRIES:
            log.debug('[ident_jussi] SERVER IS DEAD')
            raise ServerDead(f'{host} did not respond properly after {tries} tries')
        try:
            log.debug('{} ident_jussi attempt {}'.format(host, tries))
            start = time.time()
            tries += 1
            srvtype = 'err'
            try:
                async with httpx.AsyncClient() as s:
                    res = await s.get(host)
                    res.raise_for_status()
                    j = res.json()
                srvtype = self._ident_response(j)
            except httpx.HTTPError as e:
                if '426 Client Error' in str(e): raise e
                srvtype = self._ident_response(str(e.response.content))
                if srvtype is None:
                    raise e
            end = time.time()
            runtime = end - start
            # if we made it this far, we're fine :)
            results = RPCBenchResult(result=srvtype, time_taken=runtime, tries=tries)
            log.debug(f'{Fore.GREEN}[{host}] Successful request for ident_jussi{Fore.RESET}')
            return results
        except Exception as e:
            self.last_exception = e
            if 'HTTPError' in str(type(e)) and '426 Client Error' in str(e):
                raise ServerDead(f'Server {host} only supports websockets', orig_ex=self.last_exception, host=host)
            log.debug(f'{Fore.RED} [ident_jussi] {host} attempt {tries} failed. Message: {type(e)} {str(e)} {Fore.RESET}')
            await asyncio.sleep(RETRY_DELAY)
            return await self._ident_jussi(host=host, tries=tries)
