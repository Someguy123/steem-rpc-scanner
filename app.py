#!/usr/bin/env python3
# Steem node RPC scanner
# by @someguy123
# version 1.0
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
import logging

parser = argparse.ArgumentParser(description='Scan RPC nodes in nodes.txt')
parser.add_argument('-v', metavar='verbose', dest='verbose', type=bool, 
                    default=False, help='display debugging')
args = parser.parse_args()

verbose = args.verbose
if verbose:
    Logger.setLevel('debug')
# s = requests.Session()
s = AsyncSession(n=20)

RPC_TIMEOUT = 10
MAX_TRIES = 5
# nodes to be specified line by line. format: http://gtg.steem.house:8090
NODE_LIST_FILE = "nodes.txt"
NODE_LIST = open(NODE_LIST_FILE, 'r').readlines()
NODE_LIST = [n.strip() for n in NODE_LIST]
node_status = {}

class ServerDead(BaseException):
    pass

class NodePlug:
    @defer.inlineCallbacks
    def tryNode(self, reactor, host, method, params=[]):
        # self.dfr = defer.Deferred()
        self.reactor = reactor
        # self._tryNode(host, method, params)
        try:
            tn = yield self._tryNode(host, method, params)
            return tn
        except Exception as e:
            logging.debug('caught in tryNode and raised')
            raise e
    
    @defer.inlineCallbacks
    def _tryNode(self, host, method, params=[], tries=0):
        # dfr = self.dfr
        if tries >= MAX_TRIES:
            # dfr.errback(ServerDead('{} did not respond properly after {} tries'.format(host, tries)))
            # return dfr
            logging.debug('SERVER IS DEAD')
            raise ServerDead('{} did not respond properly after {} tries'.format(host, tries))
            # yield dfr
        try:
            logging.info('{} {} attempt {}'.format(host, method, tries))
            start = time.time()
            tries += 1
            res = yield _rpc(host, method, params)

            end = time.time()
            runtime = end - start

            # if we made it this far, we're fine :)
            success = True
            results = [res, runtime, tries]
            # dfr.callback(tuple(results))
            logging.debug(Fore.GREEN + '[{}] Successful request for {}'.format(host, method) + Fore.RESET)
            # print('RETURNING RESULTS FOR {}: {} (len {})'.format(host, method, len(results)))
            # return tuple(results)
            # yield dfr
            # dfr.callback(tuple(results))
            return tuple(results)
        except Exception as e:
            if 'HTTPError' in str(type(e)) and '426 Client Error' in str(e):
                raise ServerDead('Server {} only supports websockets'.format(host))
            logging.info('{red}{} attempt {} failed. Message:'.format(host, tries, red=Fore.RED), type(e), str(e), Fore.RESET)
            dl = yield deferLater(self.reactor, 10, self._tryNode, host, method, params, tries)
            return dl
            # flow.Cooperate()
            # don't try again on this same node for a few seconds
            # rec = yield self.reactor.callLater(3, self._tryNode, host, method, params, tries)
            # print("Reactor yielded:", rec)
            # return rec
            # yield dfr
        # return dfr

    

@inlineCallbacks
def rpc(reactor, host, method, params=[]):
    """
    Handles an RPC request, with automatic re-trying
    and timing.
    :returns: tuple (response, time_taken_sec, tries)
    :raises: ServerDead - tried too many times and failed
    """
    # tries = 0
    logging.info(Fore.BLUE + 'Attempting method {method} on server {host}. Will try {tries} times'.format(
        tries=MAX_TRIES, host=host, method=method
    ) + Fore.RESET)
    # d = defer.Deferred()
    np = NodePlug()
    try:
        d = yield np.tryNode(reactor, host, method, params)
    except ServerDead as e:
        logging.debug('caught in rpc and raised')
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
    conf_nodes = []
    prop_nodes = []
    nodes = NODE_LIST
    print('Scanning nodes... Please wait...')
    for node in nodes:
        node_status[node] = dict(
            raw={}, timing={}, tries={},
            current_block='error', block_time='error', version='error'
            )
        logging.info('Scanning node ', node)
        conf_nodes.append((node, rpc(reactor, node, 'get_config')))
        prop_nodes.append((node, rpc(reactor, node, 'get_dynamic_global_properties')))
    req_success = 0    
    for host, cfdata in conf_nodes:
        ns = node_status[host]        
        try:
            # config, config_time, config_tries = rpc(node, 'get_config')
            c = yield cfdata
            logging.debug(Fore.LIGHTMAGENTA_EX + 'cfdata length:', len(c), Fore.RESET)
            config, config_time, config_tries = c
            logging.info(Fore.GREEN + 'Successfully obtained config' + Fore.RESET)

            ns['raw']['config'] = config
            ns['timing']['config'] = config_time
            ns['tries']['config'] = config_tries
            ns['version'] = config.get('STEEM_BLOCKCHAIN_VERSION', config.get('STEEMIT_BLOCKCHAIN_VERSION', 'Unknown'))
            req_success += 1
        except ServerDead as e:
            logging.error(Fore.RED + '[load config]' + str(e) + Fore.RESET)
            if "only supports websockets" in str(e):
                ns['err_reason'] = 'WS Only'
        except Exception as e:
            logging.warning(Fore.RED + 'Unknown error occurred (conf)...' + Fore.RESET)
            logging.warning(type(e), str(e))
    for host, prdata in prop_nodes:
        ns = node_status[host]
        try:
            # head_block_number
            # time (UTC)
            props, props_time, props_tries = yield prdata
            logging.debug(Fore.GREEN + 'Successfully obtained props' + Fore.RESET)
            ns['raw']['props'] = props
            ns['timing']['props'] = props_time
            ns['tries']['props'] = props_tries
            ns['current_block'] = props.get('head_block_number', 'Unknown')
            ns['block_time'] = props.get('time', 'Unknown')
            req_success += 1

        except ServerDead as e:
            logging.error(Fore.RED + '[load props]' + str(e) + Fore.RESET)
            # logging.error(str(e))
            if "only supports websockets" in str(e):
                ns['err_reason'] = 'WS Only'
        except Exception as e:
            logging.error(Fore.RED + 'Unknown error occurred (prop)...' + Fore.RESET)
            logging.error(type(e), str(e))
    
    print_nodes(node_status)

def print_nodes(list_nodes):
    print(Fore.BLUE, end='', sep='')
    print('{:<40}{:<10}{:<15}{:<25}{:<15}{:<10}{}'.format('Server', 'Status', 'Head Block', 'Block Time', 'Version', 'Res Time', 'Avg Retries'))
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
        print('{:<40}{:<15}{:<15}{:<25}{:<15}{:<10}{}'.format(
            host, 
            status,
            data['current_block'],
            data['block_time'],
            data['version'],
            avg_res,
            avg_tries
        ), Fore.RESET)

if __name__ == "__main__":
    react(scan_nodes)
