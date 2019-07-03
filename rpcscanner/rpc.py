import json
import logging
import time
import twisted.internet.reactor
from typing import Union, Tuple, Iterable
from colorama import Fore
from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks
from twisted.internet.task import deferLater
from rpcscanner.exceptions import ServerDead
from rpcscanner.core import MAX_TRIES, RPC_TIMEOUT
from requests_threads import AsyncSession

log = logging.getLogger(__name__)
s = AsyncSession(n=50)


@inlineCallbacks
def rpc(reactor, host: str, method: str, params: Union[dict, list] = None) -> Tuple[Iterable, float, int]:
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
    np = NodePlug(reactor)
    try:
        d = yield np.try_node(host, method, params)
    except ServerDead as e:
        log.debug('caught in rpc and raised')
        raise e

    # return tuple(results)
    return d


@inlineCallbacks
def identify_node(reactor, host):
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
    np = NodePlug(reactor)
    try:
        d = yield np.ident_jussi(host)
        log.info('Successfully identified %s', host)
    except ServerDead as e:
        log.debug('caught in identify_node and raised')
        raise e

    # return tuple(results)
    return d


@inlineCallbacks
def _rpc(host: str, method: str, params=None):
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
    res = yield s.post(host, data=json.dumps(payload), headers=headers, timeout=RPC_TIMEOUT)
    res.raise_for_status()
    # print(res.text[0:10])
    res = res.json()
    if 'result' not in res:
        # print(res)
        raise Exception('No result')

    return res['result']


class NodePlug:
    def __init__(self, reactor: twisted.internet.reactor):
        self.reactor = reactor

    @defer.inlineCallbacks
    def try_node(self, host, method, params=None):
        params = [] if params is None else params
        # self.reactor = reactor
        try:
            tn = yield self._try_node(host, method, params)
            return tn
        except Exception as e:
            log.debug('caught in try_node and raised')
            raise e

    @defer.inlineCallbacks
    def _try_node(self, host, method, params: Union[dict, list] = None, tries=0):
        params = [] if params is None else params
        if tries >= MAX_TRIES:
            log.debug('SERVER IS DEAD')
            raise ServerDead('{} did not respond properly after {} tries'.format(host, tries))

        try:
            log.debug('{} {} attempt {}'.format(host, method, tries))
            start = time.time()
            tries += 1
            res = yield _rpc(host, method, params)

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
            dl = yield deferLater(self.reactor, 10, self._try_node, host, method, params, tries)
            return dl

    @defer.inlineCallbacks
    def ident_jussi(self, host):
        # self.reactor = reactor
        try:
            tn = yield self._ident_jussi(host)
            return tn
        except Exception as e:
            log.debug('caught in ident_jussi and raised')
            raise e

    @defer.inlineCallbacks
    def _ident_jussi(self, host, tries=0):
        if tries >= MAX_TRIES:
            log.debug('[ident_jussi] SERVER IS DEAD')
            raise ServerDead('{} did not respond properly after {} tries'.format(host, tries))
        try:
            log.debug('{} ident_jussi attempt {}'.format(host, tries))
            start = time.time()
            tries += 1
            res = yield s.get(host)
            res.raise_for_status()
            j = res.json()

            end = time.time()
            runtime = end - start
            srvtype = 'err'
            if 'jussi_num' in j:
                srvtype = 'jussi'
            elif 'error' in j and 'message' in j['error']:
                if j['error']['message'] == 'End Of File:stringstream':
                    srvtype = 'appbase'
            # if we made it this far, we're fine :)
            results = [srvtype, runtime, tries]
            log.debug(Fore.GREEN + '[{}] Successful request for ident_jussi'.format(host) + Fore.RESET)
            return tuple(results)
        except Exception as e:
            if 'HTTPError' in str(type(e)) and '426 Client Error' in str(e):
                raise ServerDead('Server {} only supports websockets'.format(host))
            log.debug('%s [ident_jussi] %s attempt %d failed. Message: %s %s %s', Fore.RED, host, tries, type(e), str(e), Fore.RESET)
            dl = yield deferLater(self.reactor, 10, self._ident_jussi, host, tries)
            return dl
