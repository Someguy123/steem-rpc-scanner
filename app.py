#!/usr/bin/env python3
# Steem node RPC scanner
# by @someguy123
# version 1.1
# Python 3.7.0 or higher recommended
from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks
from twisted.internet.task import react, deferLater
from requests_threads import AsyncSession
import json
import time
from colorama import Fore, Back
import asyncio
import argparse
from privex.loghelper import LogHelper
import logging
import signal

parser = argparse.ArgumentParser(description='Scan RPC nodes from a list of URLs to determine their last block, version, reliability, and response time.')
parser.add_argument('-v', dest='verbose', action='store_true', default=False, help='display debugging')
parser.add_argument('-q', dest='quiet', action='store_true', default=False, help='only show warnings or worse')
parser.add_argument('-f', dest='nodefile', default='nodes.txt', help='specify a custom file to read nodes from (default: nodes.txt)')
parser.set_defaults(verbose=False, quiet=False)
args = parser.parse_args()

debug_level = logging.INFO

verbose = args.verbose
if verbose:
    print('Verbose mode enabled.')
    debug_level = logging.DEBUG
elif args.quiet:
    debug_level = logging.WARNING
else:
    print("For more verbose logging (such as detailed scanning actions), use `./app.py -v`")
    print("For less output, use -q for quiet mode (display only warnings and errors)")

f = logging.Formatter('[%(asctime)s]: %(funcName)-14s : %(levelname)-8s:: %(message)s')
lh = LogHelper(handler_level=debug_level, formatter=f)
lh.add_console_handler()
log = lh.get_logger()

# s = requests.Session()
s = AsyncSession(n=50)

RPC_TIMEOUT = 5
MAX_TRIES = 5
# nodes to be specified line by line. format: http://gtg.steem.house:8090
# NODE_LIST_FILE = "nodes.txt"
NODE_LIST = open(args.nodefile, 'r').readlines()
NODE_LIST = [n.strip() for n in NODE_LIST]
# Allow nodes to be commented out with # symbol
NODE_LIST = [n for n in NODE_LIST if n[0] != '#']
node_status = {}

class ServerDead(BaseException):
    pass

class NodePlug:
    @defer.inlineCallbacks
    def tryNode(self, reactor, host, method, params=[]):
        self.reactor = reactor
        try:
            tn = yield self._tryNode(host, method, params)
            return tn
        except Exception as e:
            log.debug('caught in tryNode and raised')
            raise e
    
    @defer.inlineCallbacks
    def _tryNode(self, host, method, params=[], tries=0):
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
            success = True
            results = [res, runtime, tries]
            log.debug(Fore.GREEN + '[{}] Successful request for {}'.format(host, method) + Fore.RESET)
            return tuple(results)
        except Exception as e:
            if 'HTTPError' in str(type(e)) and '426 Client Error' in str(e):
                raise ServerDead('Server {} only supports websockets'.format(host))
            log.info('%s [%s] %s attempt %d failed. Message: %s %s %s', Fore.RED, method, host, tries, type(e), str(e), Fore.RESET)
            dl = yield deferLater(self.reactor, 10, self._tryNode, host, method, params, tries)
            return dl

    @defer.inlineCallbacks
    def identJussi(self, reactor, host):
        self.reactor = reactor
        try:
            tn = yield self._identJussi(host)
            return tn
        except Exception as e:
            log.debug('caught in identJussi and raised')
            raise e
    
    @defer.inlineCallbacks
    def _identJussi(self, host, tries=0):
        if tries >= MAX_TRIES:
            log.debug('[identJussi] SERVER IS DEAD')
            raise ServerDead('{} did not respond properly after {} tries'.format(host, tries))
        try:
            log.debug('{} identJussi attempt {}'.format(host, tries))
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
            success = True
            results = [srvtype, runtime, tries]
            log.debug(Fore.GREEN + '[{}] Successful request for identJussi'.format(host) + Fore.RESET)
            return tuple(results)
        except Exception as e:
            if 'HTTPError' in str(type(e)) and '426 Client Error' in str(e):
                raise ServerDead('Server {} only supports websockets'.format(host))
            log.debug('%s [identJussi] %s attempt %d failed. Message: %s %s %s', Fore.RED, host, tries, type(e), str(e), Fore.RESET)
            dl = yield deferLater(self.reactor, 10, self._identJussi, host, tries)
            return dl

    

@inlineCallbacks
def rpc(reactor, host, method, params=[]):
    """
    Handles an RPC request, with automatic re-trying
    and timing.
    :returns: tuple (response, time_taken_sec, tries)
    :raises: ServerDead - tried too many times and failed
    """
    # tries = 0
    log.debug(Fore.BLUE + 'Attempting method {method} on server {host}. Will try {tries} times'.format(
        tries=MAX_TRIES, host=host, method=method
    ) + Fore.RESET)
    # d = defer.Deferred()
    np = NodePlug()
    try:
        d = yield np.tryNode(reactor, host, method, params)
    except ServerDead as e:
        log.debug('caught in rpc and raised')
        raise e

    # return tuple(results)
    return d

@inlineCallbacks
def identifyNode(reactor, host):
    """
    Detects a server type
    :returns: tuple (servtype, time_taken_sec, tries)
    :raises: ServerDead - tried too many times and failed
    """
    # tries = 0
    log.debug(Fore.BLUE + 'Attempting method identifyNode on server {host}. Will try {tries} times'.format(
        tries=MAX_TRIES, host=host
    ) + Fore.RESET)
    # d = defer.Deferred()
    np = NodePlug()
    try:
        d = yield np.identJussi(reactor, host)
    except ServerDead as e:
        log.debug('caught in identifyNode and raised')
        raise e

    # return tuple(results)
    return d


@inlineCallbacks
def _rpc(host, method, params=[]):
    headers = {
        # 'Host': domain,
        'content-type': 'application/x-www-form-urlencoded'
    }
    payload = {
        "method": method,
        "params": [],
        "jsonrpc": "2.0",
        "id": 1,
    }
    res = yield s.post(host, 
        data=json.dumps(payload),
        headers=headers, timeout=RPC_TIMEOUT
    )
    res.raise_for_status()
    # print(res.text[0:10])
    res = res.json()
    if 'result' not in res: 
        # print(res)
        raise Exception('No result')
    
    return res['result']

@inlineCallbacks
def scan_nodes(reactor):
    ident_nodes = []
    conf_nodes = []
    prop_nodes = []
    up_nodes = []
    nodes = NODE_LIST
    print('Scanning nodes... Please wait...')
    print('{}[Stage 1 / 4] Identifying node types (jussi/appbase){}'.format(Fore.GREEN, Fore.RESET))
    for node in nodes:
        node_status[node] = dict(
            raw={}, timing={}, tries={},
            current_block='error', block_time='error', version='error',
            srvtype='err'
            )
        ident_nodes.append((node, identifyNode(reactor, node)))
        log.info('Identifying %s', node)
    req_success = 0

    for host, id_data in ident_nodes:
        ns = node_status[host]        
        try:
            c = yield id_data
            ident, ident_time, ident_tries = c
            log.info(Fore.GREEN + 'Successfully obtained server type for node %s' + Fore.RESET, host)

            ns['srvtype'] = ident
            ns['timing']['ident'] = ident_time
            ns['tries']['ident'] = ident_tries
            if ns['srvtype'] == 'jussi':
                log.info('Server {} is JUSSI'.format(host))
                up_nodes.append((host, ns['srvtype'], rpc(reactor, host, 'get_dynamic_global_properties')))
            if ns['srvtype'] == 'appbase':
                log.info('Server {} is APPBASE (no jussi)'.format(host))
                up_nodes.append((host, ns['srvtype'], rpc(reactor, host, 'condenser_api.get_dynamic_global_properties')))
            req_success += 1
        except ServerDead as e:
            log.error(Fore.RED + '[ident jussi]' + str(e) + Fore.RESET)
            if "only supports websockets" in str(e):
                ns['err_reason'] = 'WS Only'
        except Exception as e:
            log.warning(Fore.RED + 'Unknown error occurred (ident jussi)...' + Fore.RESET)
            log.warning('[%s] %s', type(e), str(e))
    
    print('{}[Stage 2 / 4] Filtering out bad nodes{}'.format(Fore.GREEN, Fore.RESET))    
    for host, srvtype, blkdata in up_nodes:
        try:
            c = yield blkdata
            # if it didn't except, then we're probably fine. we don't care about the block data
            # because it will be outdated due to bad nodes. will get it later
            if srvtype == 'jussi':
                conf_nodes.append((host, rpc(reactor, host, 'get_config')))
                prop_nodes.append((host, rpc(reactor, host, 'get_dynamic_global_properties')))
            if srvtype == 'appbase':
                conf_nodes.append((host, rpc(reactor, host, 'condenser_api.get_config')))
                prop_nodes.append((host, rpc(reactor, host, 'condenser_api.get_dynamic_global_properties')))
            log.info(Fore.GREEN + 'Node %s seems fine' + Fore.RESET, host)
        except ServerDead as e:
            log.error(Fore.RED + '[badnodefilter]' + str(e) + Fore.RESET)
            if "only supports websockets" in str(e):
                ns['err_reason'] = 'WS Only'
        except Exception as e:
            log.warning(Fore.RED + 'Unknown error occurred (badnodefilter)...' + Fore.RESET)
            log.warning('[%s] %s', type(e), str(e))
    
    print('{}[Stage 3 / 4] Obtaining steemd versions {}'.format(Fore.GREEN, Fore.RESET))    
    for host, cfdata in conf_nodes:
        ns = node_status[host]        
        try:
            # config, config_time, config_tries = rpc(node, 'get_config')
            c = yield cfdata
            config, config_time, config_tries = c
            log.info(Fore.GREEN + 'Successfully obtained config for node %s' + Fore.RESET, host)

            ns['raw']['config'] = config
            ns['timing']['config'] = config_time
            ns['tries']['config'] = config_tries
            ns['version'] = config.get('STEEM_BLOCKCHAIN_VERSION', config.get('STEEMIT_BLOCKCHAIN_VERSION', 'Unknown'))
            req_success += 1
        except ServerDead as e:
            log.error(Fore.RED + '[load config]' + str(e) + Fore.RESET)
            if "only supports websockets" in str(e):
                ns['err_reason'] = 'WS Only'
        except Exception as e:
            log.warning(Fore.RED + 'Unknown error occurred (conf)...' + Fore.RESET)
            log.warning('[%s] %s', type(e), str(e))
    
    print('{}[Stage 4 / 4] Checking current block / block time{}'.format(Fore.GREEN, Fore.RESET))    
    for host, prdata in prop_nodes:
        ns = node_status[host]
        try:
            # head_block_number
            # time (UTC)
            props, props_time, props_tries = yield prdata
            log.debug(Fore.GREEN + 'Successfully obtained props' + Fore.RESET)
            ns['raw']['props'] = props
            ns['timing']['props'] = props_time
            ns['tries']['props'] = props_tries
            ns['current_block'] = props.get('head_block_number', 'Unknown')
            ns['block_time'] = props.get('time', 'Unknown')
            req_success += 1

        except ServerDead as e:
            log.error(Fore.RED + '[load props]' + str(e) + Fore.RESET)
            # log.error(str(e))
            if "only supports websockets" in str(e):
                ns['err_reason'] = 'WS Only'
        except Exception as e:
            log.warning(Fore.RED + 'Unknown error occurred (prop)...' + Fore.RESET)
            log.warning('[%s] %s', type(e), str(e))
    
    print_nodes(node_status)

def print_nodes(list_nodes):
    print(Fore.BLUE, '(S) - SSL, (H) - HTTP : (A) - normal appbase (J) - jussi', Fore.RESET)
    print(Fore.BLUE, end='', sep='')
    print('{:<45}{:<10}{:<15}{:<25}{:<15}{:<10}{}'.format('Server', 'Status', 'Head Block', 'Block Time', 'Version', 'Res Time', 'Avg Retries'))
    print(Fore.RESET, end='', sep='')
    for host, data in list_nodes.items():
        statuses = {
            0: Fore.RED + "DEAD",
            1: Fore.YELLOW + "UNSTABLE",
            2: Fore.GREEN + "Online",
        }
        status = statuses[len(data['raw'])]
        avg_res = 'error'
        if len(data['timing']) > 0:
            time_total = 0.0
            for time_type, time in data['timing'].items():
                time_total += time
            avg_res = time_total / len(data['timing'])
            avg_res = '{:.2f}'.format(avg_res)
        
        avg_tries = 'error'
        if len(data['tries']) > 0:
            tries_total = 0
            for tries_type, tries in data['tries'].items():
                tries_total += tries
            avg_tries = tries_total / len(data['tries'])
            avg_tries = '{:.2f}'.format(avg_tries)
        if 'err_reason' in data:
            status = Fore.YELLOW + data['err_reason']
        host = host.replace('https://', '(S)')
        host = host.replace('http://', '(H)')
        if data['srvtype'] == 'jussi':
            host = "{}(J){} {}".format(Fore.GREEN, Fore.RESET, host)
        elif data['srvtype'] == 'appbase':
            host = "{}(A){} {}".format(Fore.BLUE, Fore.RESET, host)
        else:
            host = "{}(?){} {}".format(Fore.RED, Fore.RESET, host)

        print('{:<55}{:<15}{:<15}{:<25}{:<15}{:<10}{}'.format(
            host, 
            status,
            data['current_block'],
            data['block_time'],
            data['version'],
            avg_res,
            avg_tries
        ), Fore.RESET)

if __name__ == "__main__":
    # Make CTRL-C work properly with Twisted's Reactor
    # https://stackoverflow.com/a/4126412/2648583
    signal.signal(signal.SIGINT, signal.default_int_handler)
    react(scan_nodes)
