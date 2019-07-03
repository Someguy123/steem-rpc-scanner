from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Tuple

import twisted.internet.reactor
import logging
from colorama import Fore
from dateutil.parser import parse
from privex.helpers import empty
from twisted.internet.defer import inlineCallbacks
from rpcscanner.MethodTests import MethodTests
from rpcscanner.core import TEST_PLUGINS_LIST
from rpcscanner.rpc import rpc, identify_node
from rpcscanner.exceptions import ServerDead
from rpcscanner import settings

log = logging.getLogger(__name__)


@dataclass
class NodeStatus:
    host: str
    raw: dict
    timing: dict
    tries: dict
    plugins: list
    err_reason: str = None
    srvtype: str = 'Unknown'
    current_block: int = None
    block_time: datetime = None
    version: str = None

    _statuses = {
        0: "Dead",
        1: "Unstable",
        2: "Online",
    }

    @property
    def status(self) -> int:
        """Status of the node as a number from 0 to 2"""
        return len(self.raw)

    @property
    def status_human(self) -> str:
        """Status of the node as a description, e.g. dead, unstable, online"""
        return self._statuses[self.status]

    @property
    def total_tries(self) -> int:
        """How many retries were required to get the data for this node?"""
        tries_total = 0
        for tries_type, tries in self.tries.items():
            tries_total += tries
        return tries_total

    @property
    def avg_tries(self) -> str:
        """The average amount of tries required per API call to get a valid response, as a 2 DP formatted string"""
        return '{:.2f}'.format(self.total_tries / len(self.tries))

    @property
    def plugin_counts(self) -> Tuple[int, int]:
        """Returns as a tuple: how many plugins worked, and how many were tested"""
        return len(self.plugins), len(TEST_PLUGINS_LIST)

    def __post_init__(self):
        bt = self.block_time
        if not empty(bt):
            if type(bt) is str and bt.lower() == 'error':
                self.block_time = None
                return
            self.block_time = parse(bt)


class RPCScanner:

    def __init__(self, reactor: twisted.internet.reactor, nodes: list):
        self.conf_nodes = []
        self.prop_nodes = []
        self.reactor = reactor
        self.node_status = {}
        self.ident_nodes = []
        self.up_nodes = []
        self.nodes = nodes
        self.req_success = 0

    @inlineCallbacks
    def scan_nodes(self, quiet=False):
        def p(*args):
            if not quiet:
                print(*args)

        reactor = self.reactor
        p('Scanning nodes... Please wait...')
        p('{}[Stage 1 / 4] Identifying node types (jussi/appbase){}'.format(Fore.GREEN, Fore.RESET))
        for node in self.nodes:
            self.node_status[node] = dict(
                raw={}, timing={}, tries={}, plugins=[],
                current_block='error', block_time='error', version='error',
                srvtype='err'
                )
            self.ident_nodes.append((node, identify_node(reactor, node)))

        yield from self.identify_nodes()

        p('{}[Stage 2 / 4] Filtering out bad nodes{}'.format(Fore.GREEN, Fore.RESET))
        yield from self.filter_badnodes()

        p('{}[Stage 3 / 4] Obtaining steemd versions {}'.format(Fore.GREEN, Fore.RESET))
        yield from self.scan_versions()

        p('{}[Stage 4 / 4] Checking current block / block time{}'.format(Fore.GREEN, Fore.RESET))
        yield from self.scan_block_info()

        if settings.plugins:
            p('{}[Thorough Plugin Check] User specified --plugins. Now running thorough plugin tests for '
              'alive nodes.{}'.format(Fore.GREEN, Fore.RESET))
            for host, data in self.node_status.items():
                status = len(data['raw'])
                if status == 0:
                    log.info(f'Skipping node {host} as it appears to be dead.')
                    continue
                log.info(f'{Fore.BLUE} > Running plugin tests for node {host} ...{Fore.RESET}')
                mt = MethodTests(host, reactor)
                for plugin in TEST_PLUGINS_LIST:
                    pt = yield self.plugin_test(host, plugin, mt)
                log.info(f'{Fore.GREEN} (+) Finished plugin tests for node {host} ... {Fore.RESET}')


    @inlineCallbacks
    def plugin_test(self, host: str, plugin_name: str, mt: MethodTests):
        ns = self.node_status[host]
        try:
            log.info(f' >>> Testing {plugin_name} for node {host} ...')
            res = yield mt.test(plugin_name)
            ns['plugins'].append(plugin_name)
            log.info(f'{Fore.GREEN} +++ The API {plugin_name} is functioning for node {host}{Fore.RESET}')
            return res
        except Exception as e:
            log.error(
                f'{Fore.RED} !!! The API {plugin_name} test failed for node {host}: {type(e)} {str(e)} {Fore.RESET}')

    @inlineCallbacks
    def identify_nodes(self):
        reactor = self.reactor
        for host, id_data in self.ident_nodes:
            ns = self.node_status[host]
            try:
                c = yield id_data
                ident, ident_time, ident_tries = c
                log.info(Fore.GREEN + 'Successfully obtained server type for node %s' + Fore.RESET, host)

                ns['srvtype'] = ident
                ns['timing']['ident'] = ident_time
                ns['tries']['ident'] = ident_tries
                if ns['srvtype'] == 'jussi':
                    log.info('Server {} is JUSSI'.format(host))
                    self.up_nodes.append((host, ns['srvtype'], rpc(reactor, host, 'get_dynamic_global_properties')))
                if ns['srvtype'] == 'appbase':
                    log.info('Server {} is APPBASE (no jussi)'.format(host))
                    self.up_nodes.append(
                        (host, ns['srvtype'], rpc(reactor, host, 'condenser_api.get_dynamic_global_properties')))
                self.req_success += 1
            except ServerDead as e:
                log.error(Fore.RED + '[ident jussi]' + str(e) + Fore.RESET)
                if "only supports websockets" in str(e):
                    ns['err_reason'] = 'WS Only'
            except Exception as e:
                log.warning(Fore.RED + 'Unknown error occurred (ident jussi)...' + Fore.RESET)
                log.warning('[%s] %s', type(e), str(e))

    @inlineCallbacks
    def filter_badnodes(self):
        prop_nodes = self.prop_nodes
        conf_nodes = self.conf_nodes
        reactor = self.reactor
        for host, srvtype, blkdata in self.up_nodes:
            ns = self.node_status[host]
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
        return prop_nodes, conf_nodes

    @inlineCallbacks
    def scan_block_info(self):
        for host, prdata in self.prop_nodes:
            ns = self.node_status[host]
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
                self.req_success += 1

            except ServerDead as e:
                log.error(Fore.RED + '[load props]' + str(e) + Fore.RESET)
                # log.error(str(e))
                if "only supports websockets" in str(e):
                    ns['err_reason'] = 'WS Only'
            except Exception as e:
                log.warning(Fore.RED + 'Unknown error occurred (prop)...' + Fore.RESET)
                log.warning('[%s] %s', type(e), str(e))

    @inlineCallbacks
    def scan_versions(self):
        for host, cfdata in self.conf_nodes:
            ns = self.node_status[host]
            try:
                # config, config_time, config_tries = rpc(node, 'get_config')
                c = yield cfdata
                config, config_time, config_tries = c
                log.info(Fore.GREEN + 'Successfully obtained config for node %s' + Fore.RESET, host)

                ns['raw']['config'] = config
                ns['timing']['config'] = config_time
                ns['tries']['config'] = config_tries
                ns['version'] = config.get('STEEM_BLOCKCHAIN_VERSION', config.get('STEEMIT_BLOCKCHAIN_VERSION', 'Unknown'))
                self.req_success += 1
            except ServerDead as e:
                log.error(Fore.RED + '[load config]' + str(e) + Fore.RESET)
                if "only supports websockets" in str(e):
                    ns['err_reason'] = 'WS Only'
            except Exception as e:
                log.warning(Fore.RED + 'Unknown error occurred (conf)...' + Fore.RESET)
                log.warning('[%s] %s', type(e), str(e))

    @property
    def node_objs(self) -> List[NodeStatus]:
        return [NodeStatus(host=h, **n) for h, n in self.node_status.items()]

    def get_node(self, node: str) -> NodeStatus:
        n = self.node_status[node]
        return NodeStatus(host=node, **n)

    def print_nodes(self):
        list_nodes = self.node_status
        print(Fore.BLUE, '(S) - SSL, (H) - HTTP : (A) - normal appbase (J) - jussi', Fore.RESET)
        print(Fore.BLUE, end='', sep='')
        fmt_params = ['Server', 'Status', 'Head Block', 'Block Time', 'Version', 'Res Time', 'Avg Retries']
        fmt_str = '{:<45}{:<10}{:<15}{:<25}{:<15}{:<10}{:<15}'
        if settings.plugins:
            fmt_str += '{:<15}'
            fmt_params.append('Plugin Tests')
        print(fmt_str.format(*fmt_params))
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
            fmt_params = [
                host, status, data['current_block'], data['block_time'],
                data['version'], avg_res, avg_tries
            ]
            fmt_str = '{:<55}{:<15}{:<15}{:<25}{:<15}{:<10}{:<15}'
            if settings.plugins:
                fmt_str += '{:<15}'
                plg, ttl_plg = len(data['plugins']), len(TEST_PLUGINS_LIST)

                f_plugins = f'{plg} / {ttl_plg}'
                if plg < (ttl_plg // 2): f_plugins = f'{Fore.RED}{f_plugins}'
                elif plg < ttl_plg: f_plugins = f'{Fore.YELLOW}{f_plugins}'
                elif plg == ttl_plg: f_plugins = f'{Fore.GREEN}{f_plugins}'

                fmt_params.append(f'{f_plugins}{Fore.RESET}')
            print(fmt_str.format(*fmt_params), Fore.RESET)



