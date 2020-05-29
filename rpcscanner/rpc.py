import asyncio
import json
import logging
import time
import httpx
from typing import Union, Tuple, Iterable, Mapping, Optional
from colorama import Fore
from rpcscanner.exceptions import ServerDead
from rpcscanner.settings import MAX_TRIES, RPC_TIMEOUT, RETRY_DELAY

log = logging.getLogger(__name__)
# s = AsyncSession(n=50)


async def rpc(host: str, method: str, params: Union[dict, list] = None) -> Tuple[Union[list, dict], float, int]:
    """
    Handles an RPC request, with automatic re-trying
    and timing.
    :returns: tuple (response, time_taken_sec, tries)
    :raises: ServerDead - tried too many times and failed
    """
    params = [] if params is None else params
    # tries = 0
    log.debug(Fore.BLUE + 'Attempting method {method} on server {host}. Will try {tries} times'.format(
        tries=MAX_TRIES, host=host, method=method
    ) + Fore.RESET)
    # d = defer.Deferred()
    np = NodePlug()
    try:
        d = await np.try_node(host, method, params)
    except ServerDead as e:
        log.debug('caught in rpc and raised')
        raise e

    # return tuple(results)
    return d


async def identify_node(host):
    """
    Detects a server type
    :returns: tuple (servtype, time_taken_sec, tries)
    :raises: ServerDead - tried too many times and failed
    """
    # tries = 0
    log.info('Identifying %s', host)
    log.debug(Fore.BLUE + 'Attempting method identify_node on server {host}. Will try {tries} times'.format(
        tries=MAX_TRIES, host=host
    ) + Fore.RESET)
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


async def _rpc(host: str, method: str, params=None):
    params = [] if params is None else params
    headers = {
        # 'Host': domain,
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
    
    if 'result' not in j:
        # print(res)
        raise Exception('No result')

    return j['result']


class NodePlug:
    def __init__(self):
        # self.reactor = reactor
        pass
    
    async def try_node(self, host, method, params=None):
        params = [] if params is None else params
        # self.reactor = reactor
        try:
            tn = await self._try_node(host, method, params)
            return tn
        except Exception as e:
            log.debug('caught in try_node and raised')
            raise e

    async def _try_node(self, host, method, params: Union[dict, list] = None, tries=0):
        params = [] if params is None else params
        if tries >= MAX_TRIES:
            log.debug('SERVER IS DEAD')
            raise ServerDead('{} did not respond properly after {} tries'.format(host, tries))

        try:
            log.debug('{} {} attempt {}'.format(host, method, tries))
            start = time.time()
            tries += 1
            res = await _rpc(host, method, params)

            end = time.time()
            runtime = end - start

            # if we made it this far, we're fine :)
            results = [res, runtime, tries]
            log.debug(Fore.GREEN + '[{}] Successful request for {}'.format(host, method) + Fore.RESET)
            return tuple(results)
        except Exception as e:
            if 'HTTPError' in str(type(e)) and '426 Client Error' in str(e):
                raise ServerDead('Server {} only supports websockets'.format(host))
            log.info('%s [%s] %s attempt %d failed. Message: %s %s %s', Fore.RED, method, host, tries, type(e), str(e), Fore.RESET)
            # dl = yield deferLater(self.reactor, 10, self._try_node, host, method, params, tries)
            await asyncio.sleep(RETRY_DELAY)
            return await self._try_node(host, method=method, params=params, tries=tries)

    async def ident_jussi(self, host):
        # self.reactor = reactor
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
            raise ServerDead('{} did not respond properly after {} tries'.format(host, tries))
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
            results = [srvtype, runtime, tries]
            log.debug(Fore.GREEN + '[{}] Successful request for ident_jussi'.format(host) + Fore.RESET)
            return tuple(results)
        except Exception as e:
            if 'HTTPError' in str(type(e)) and '426 Client Error' in str(e):
                raise ServerDead('Server {} only supports websockets'.format(host))
            log.debug('%s [ident_jussi] %s attempt %d failed. Message: %s %s %s', Fore.RED, host, tries, type(e), str(e), Fore.RESET)
            await asyncio.sleep(RETRY_DELAY)
            return await self._ident_jussi(host=host, tries=tries)
