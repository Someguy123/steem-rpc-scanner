import asyncio
import logging
from asyncio import Task
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Coroutine, Union, Awaitable, Optional

import pytz
from colorama import Fore
from dateutil.parser import parse
from privex.helpers import empty, Dictable, DictObject, T, empty_if, convert_datetime
from rpcscanner.MethodTests import MethodTests
from rpcscanner.settings import TEST_PLUGINS_LIST
from rpcscanner.rpc import rpc, identify_node
from rpcscanner.exceptions import ServerDead
from rpcscanner import settings

log = logging.getLogger(__name__)


@dataclass
class NodeStatus(Dictable):
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
    network: str = None

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
        """How many requests were required to get the data for this node?"""
        tries_total = 0
        for tries_type, tries in self.tries.items():
            tries_total += tries
        return tries_total

    @property
    def total_retries(self) -> int:
        """How many times did we have to retry a call to get the data for this node?"""
        tries_total = 0
        for tries_type, tries in self.tries.items():
            if tries > 1:
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

    @property
    def time_behind(self) -> Optional[timedelta]:
        if empty(self.block_time): return None
        dt = convert_datetime(self.block_time).replace(tzinfo=pytz.UTC)
        now = datetime.utcnow().replace(tzinfo=pytz.UTC)
        return now - dt

    def __post_init__(self):
        bt = self.block_time
        if not empty(bt):
            if type(bt) is str and bt.lower() == 'error':
                self.block_time = None
                return
            self.block_time = parse(bt)


NETWORK_COINS = DictObject(
    STEEM='Steem', SBD='Steem', SP='Steem',
    HIVE='Hive', HBD='Hive', HP='Hive',
    GOLOS='Golos', GBG='Golos', GP='Golos',
    WLS='Whaleshares'
)

TOTAL_STAGES_TRACKED = 3
"""Amount of :class:`.RPCScanner` stages that count towards a node's status number"""


def _find_key(obj: dict, key: T, search='in', case_sensitive: bool = False) -> Optional[T]:
    if not case_sensitive: key = key.lower()
    for k in obj.keys():
        lk = k if case_sensitive else k.lower()
        if search == 'in' and key in lk: return k
        if search.startswith('end') and lk.endswith(key): return k
        if search.startswith('start') and lk.startswith(key): return k
    return None


class RPCScanner:
    nodes: List[str]
    loop: asyncio.AbstractEventLoop
    node_status: Dict[str, dict]
    up_nodes: List[Tuple[str, str, Task]]
    conf_nodes: List[Tuple[str, Task]]
    prop_nodes: List[Tuple[str, Task]]
    ver_nodes: List[Tuple[str, Task]]
    
    def __init__(self, nodes: list, loop: asyncio.AbstractEventLoop = None):
        self.conf_nodes = []
        self.prop_nodes = []
        self.ver_nodes = []
        # self.reactor = reactor
        self.node_status = {}
        self.ident_nodes = []
        self.up_nodes = []
        self.nodes = nodes
        self.req_success = 0
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop

    async def scan_nodes(self, quiet=False):
        def p(*args):
            if not quiet:
                print(*args)

        # reactor = self.reactor
        p('Scanning nodes... Please wait...')
        p('{}[Stage 1 / 4] Identifying node types (jussi/appbase){}'.format(Fore.GREEN, Fore.RESET))
        for node in self.nodes:
            self.node_status[node] = dict(
                raw={}, timing={}, tries={}, plugins=[],
                current_block='error', block_time='error', version='error',
                srvtype='err', network='err'
                )
            self.ident_nodes.append((node, self.add_task(identify_node(node))))

        await self.identify_nodes()

        p('{}[Stage 2 / 4] Filtering out bad nodes{}'.format(Fore.GREEN, Fore.RESET))
        await self.filter_badnodes()

        p('{}[Stage 3 / 4] Obtaining steemd versions {}'.format(Fore.GREEN, Fore.RESET))
        await self.scan_versions()

        p('{}[Stage 4 / 4] Checking current block / block time{}'.format(Fore.GREEN, Fore.RESET))
        await self.scan_block_info()

        if settings.plugins:
            p('{}[Thorough Plugin Check] User specified --plugins. Now running thorough plugin tests for '
              'alive nodes.{}'.format(Fore.GREEN, Fore.RESET))
            pt_list = []

            for host, data in self.node_status.items():
                status = len(data['raw'])
                if status == 0:
                    log.info(f'Skipping node {host} as it appears to be dead.')
                    continue
                log.info(f'{Fore.BLUE} > Running plugin tests for node {host} ...{Fore.RESET}')
                mt = MethodTests(host)
                for plugin in TEST_PLUGINS_LIST:
                    pt_list.append((host, self.add_task(self.plugin_test(host, plugin, mt))))
            finished = []
            for host, pt in pt_list:
                await pt
                if host not in finished:
                    finished.append(host)
                    log.info(f'{Fore.GREEN} (+) Finished plugin tests for node {host} ... {Fore.RESET}')

    async def plugin_test(self, host: str, plugin_name: str, mt: MethodTests):
        ns = self.node_status[host]
        try:
            log.debug(f' >>> Testing {plugin_name} for node {host} ...')
            res, time_secs, tries = await mt.test(plugin_name)
            ns['plugins'].append(plugin_name)
            ns['tries'][f'plugin_{plugin_name}'] = tries
            ns['timing'][f'plugin_{plugin_name}'] = time_secs
            log.debug(f'{Fore.GREEN} +++ The API {plugin_name} is functioning for node {host}{Fore.RESET}')
            return res
        except Exception as e:
            log.error(
                f'{Fore.RED} !!! The API {plugin_name} test failed for node {host}: {type(e)} {str(e)} {Fore.RESET}')

    async def identify_nodes(self):
        """
        Scans each node listed in :py:attr:`.ident_nodes` to attempt to identify whether
        the node is behind Jussi, the node is pure appbase, or the node only supports websockets.

        Outputs the result into :py:attr:`.node_status` for the given host, in the 'srvtype' key.

        Generates a list of working nodes into :py:attr:`.up_nodes` to be further processed 
        by :py:meth:`.filter_badnodes`

        """
        for host, id_data in self.ident_nodes:
            ns = self.node_status[host]
            try:
                c = await id_data
                ident, ident_time, ident_tries = c
                log.info(Fore.GREEN + 'Successfully obtained server type for node %s' + Fore.RESET, host)

                ns['srvtype'] = ident
                ns['timing']['ident'] = ident_time
                ns['tries']['ident'] = ident_tries
                if ns['srvtype'] == 'jussi':
                    log.info('Server {} is JUSSI'.format(host))
                    meth = 'condenser_api.get_dynamic_global_properties'
                elif ns['srvtype'] == 'appbase':
                    log.info('Server {} is APPBASE (no jussi)'.format(host))
                    meth = 'condenser_api.get_dynamic_global_properties'
                elif ns['srvtype'] == 'legacy':
                    log.info('Server {} is LEGACY ??? (no jussi)'.format(host))
                    meth = 'database_api.get_dynamic_global_properties'
                else:
                    raise ServerDead(f"Unknown server type {ns['srvtype']}")
                self.up_nodes.append(
                    (host, ns['srvtype'], self.rpc_task(host, meth)))
                self.req_success += 1
            except ServerDead as e:
                log.error(Fore.RED + '[ident jussi]' + str(e) + Fore.RESET)
                if "only supports websockets" in str(e):
                    ns['err_reason'] = 'WS Only'
            except Exception as e:
                log.warning(Fore.RED + 'Unknown error occurred (ident jussi)...' + Fore.RESET)
                log.warning('[%s] %s', type(e), str(e))

    def add_task(self, coro: Union[Awaitable, Coroutine]) -> Task:
        """Helper method which creates an AsyncIO task from a passed coroutine using :attr:`.loop`"""
        return self.loop.create_task(coro)
    
    def add_tasks(self, *tasks) -> List[Task]:
        """Helper method which creates a list of AsyncIO tasks from passed coroutines using :attr:`.loop`"""
        added_tasks = []
        for t in tasks:
            added_tasks.append(self.loop.create_task(t))
        return added_tasks

    def rpc_tasks(self, host: str, *calls: str, params: List[Union[dict, list]] = None) -> List[Task]:
        tasks = []
        calls = list(calls)
        for i, c in enumerate(calls):
            if not empty(params, itr=True) and len(params) > i:
                tasks.append(self.add_task(rpc(host, c, params[i])))
            else:
                tasks.append(self.add_task(rpc(host, c)))
        return tasks

    def rpc_task(self, host: str, call: str, params: Union[dict, list] = None) -> Task:
        t = self.rpc_tasks(host, call, params=params)
        return t[0]

    async def filter_badnodes(self):
        """
        Loads the dynamic properties for each host listed in :py:attr:`.up_nodes` to verify they're functioning.

        Queues up requests for `get_config` and `get_dynamic_global_properties` into :py:attr:`.conf_nodes` and
        :py:attr:`.prop_node` to be retrieved by :py:meth:`.scan_block_info` and :py:meth:`.scan_versions`
        """
        prop_nodes = self.prop_nodes
        conf_nodes = self.conf_nodes
        ver_nodes = self.ver_nodes
        for host, srvtype, blkdata in self.up_nodes:
            ns = self.node_status[host]
            try:
                c = await blkdata
                # if it didn't except, then we're probably fine. we don't care about the block data
                # because it will be outdated due to bad nodes. will get it later
                x, y = 'condenser_api.get_dynamic_global_properties', 'condenser_api.get_version'
                if srvtype == 'legacy':
                    x, y = 'database_api.get_dynamic_global_properties', 'database_api.get_config'
                tsk = self.rpc_tasks(host, x, y)
                ns['raw']['init_props'] = blkdata
                prop_nodes.append((host, tsk[0]))
                ver_nodes.append((host, tsk[1]))
                log.info(Fore.GREEN + 'Node %s seems fine' + Fore.RESET, host)
            except ServerDead as e:
                log.error(Fore.RED + '[badnodefilter]' + str(e) + Fore.RESET)
                if "only supports websockets" in str(e):
                    ns['err_reason'] = 'WS Only'
            except Exception as e:
                log.warning(Fore.RED + 'Unknown error occurred (badnodefilter)...' + Fore.RESET)
                log.warning('[%s] %s', type(e), str(e))
        return prop_nodes, conf_nodes

    async def scan_block_info(self):
        """
        Scans each host in :py:attr:`.prop_nodes` (populated by :py:meth:`.filter_badnodes` ) to obtain:
          - Current block number (head_block_number)
          - Block time (time)
        
        Stores the results in :py:attr:`.node_status`
        """
        for host, prdata in self.prop_nodes:
            ns = self.node_status[host]
            try:
                # 'head_block_number', 'time' (UTC), 'current_supply'
                props, props_time, props_tries = await prdata
                log.debug(Fore.GREEN + 'Successfully obtained props' + Fore.RESET)
                ns['raw']['props'] = props
                ns['timing']['props'] = props_time
                ns['tries']['props'] = props_tries
                ns['current_block'] = props.get('head_block_number', 'Unknown')
                ns['block_time'] = props.get('time', 'Unknown')
                # Obtain the native network coin from the current_supply, and use it to try and identify what chain this is.
                coin = props.get('current_supply', 'UNKNOWN UNKNOWN').split()[1].upper()
                ns['network'] = NETWORK_COINS.get(coin, 'Unknown')
                self.req_success += 1
            except ServerDead as e:
                log.error(Fore.RED + '[load props]' + str(e) + Fore.RESET)
                # log.error(str(e))
                if "only supports websockets" in str(e):
                    ns['err_reason'] = 'WS Only'
            except Exception as e:
                log.warning(Fore.RED + 'Unknown error occurred (prop)...' + Fore.RESET)
                log.warning('[%s] %s', type(e), str(e))

    async def scan_versions(self):
        """
        Scans each host in :py:attr:`.ver_nodes` (populated by :py:meth:`.filter_badnodes`) to
        obtain the Steem version number of each node.

        Outputs the version into the 'version' key in the node's :py:attr:`.node_status` object.
        """
        for host, cfdata in self.ver_nodes:
            ns = self.node_status[host]
            try:
                c = await cfdata
                config, config_time, config_tries = c
                log.info(Fore.GREEN + 'Successfully obtained version for node %s' + Fore.RESET, host)

                ns['raw']['config'] = config
                ns['timing']['config'] = config_time
                ns['tries']['config'] = config_tries
                ns['version'] = 'Unknown'
                # For legacy Steem-based networks, we scan the output of get_config for a key ending with blockchain_version
                if ns['srvtype'] == 'legacy':
                    k = _find_key(config, 'blockchain_version', search='ends')
                    ns['version'] = empty_if(k, 'Unknown', config.get(k, 'Unknown'))
                else:   # For more modern Steem-based networks, we can just grab blockchain_version from get_version
                    ns['version'] = config.get('blockchain_version', 'Unknown')
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
        """Return all node info from :attr:`.node_status` as a list of :class:`.NodeStatus` instances"""
        return [NodeStatus(host=h, **n) for h, n in self.node_status.items()]

    def get_node(self, node: str) -> NodeStatus:
        """Retrieve node info for an individual node from :attr:`.node_status` as a :class:`.NodeStatus` instances"""
        n = self.node_status[node]
        return NodeStatus(host=node, **n)

    def print_nodes(self):
        """
        Pretty print the node status information from :attr:`.node_status` in a colour coded table, with cleanly
        padded columns for easy readability.
        """
        list_nodes = self.node_status
        print(Fore.BLUE, '(S) - SSL, (H) - HTTP : (A) - appbase (J) - jussi (L) - legacy', Fore.RESET)
        print(Fore.BLUE, end='', sep='')
        fmt_params = ['Server', 'Status', 'Head Block', 'Block Time', 'Version', 'Network', 'Res Time', 'Avg Retries']
        fmt_str = '{:<45}{:<20}{:<15}{:<25}{:<15}{:<15}{:<10}{:<15}'
        if settings.plugins:
            fmt_str += '{:<15}'
            fmt_params.append('API Tests')
        print(fmt_str.format(*fmt_params))
        print(Fore.RESET, end='', sep='')
        for host, data in list_nodes.items():
            statuses = {
                0: Fore.RED + "DEAD",
                1: Fore.LIGHTRED_EX + "UNSTABLE",
                2: Fore.YELLOW + "Unreliable",
                3: Fore.GREEN + "Online",
            }
            data = DictObject(data)
            ns = self.get_node(host)
            # Decide on the node's status based on how many test stages the
            status = statuses[len(data['raw'])]
            
            # Calculate the average response time of this node by totalling the timing seconds, and dividing them
            # by the amount of individual timing events
            avg_res = 'error'
            if len(data['timing']) > 0:
                time_total = 0.0
                for time_type, time in data['timing'].items():
                    time_total += time
                avg_res = time_total / len(data['timing'])
                avg_res = '{:.2f}'.format(avg_res)
            
            # Calculate the average tries required per successful call by summing up the total amount of tries,
            # and dividing that by the length of the 'tries' dict (individual calls / tests that were tried)
            avg_tries = 'error'
            if len(data['tries']) > 0:
                tries_total = 0
                for tries_type, tries in data['tries'].items():
                    tries_total += tries
                avg_tries = tries_total / len(data['tries'])
                avg_tries = '{:.2f}'.format(avg_tries)
            
            if ns.time_behind:
                if ns.time_behind.total_seconds() >= 60:
                    status = f"{Fore.LIGHTRED_EX}Out-of-sync"
            
            # If there were any moderate errors while testing the node, change the status from green to yellow, and
            # change the status to the error state
            if 'err_reason' in data:
                status = Fore.YELLOW + data['err_reason']
            
            # Replace the long http:// | https:// URI prefix with a short, clean character in brackets
            host = host.replace('https://', '(S)')
            host = host.replace('http://', '(H)')
            
            # Select the appropriate coloured host type symbol based on the node's detected 'srvtype'
            def_stype = f"{Fore.RED}(?){Fore.RESET}"
            host_stypes = DictObject(
                jussi=f"{Fore.GREEN}(J){Fore.RESET}", appbase=f"{Fore.BLUE}(A){Fore.RESET}", legacy=f"{Fore.MAGENTA}(L){Fore.RESET}"
            )
            host = f"{host_stypes.get(data.srvtype, def_stype)} {host}"

            # Glue the columns together with right space padding to form the node row
            fmt_str = f'{host:<55}{status:<25}{data.current_block:<15}{data.block_time:<25}' \
                      f'{data.version:<15}{data.network:<15}{avg_res:<10}{avg_tries:<15}'
            # If plugin scanning was enabled, generate and append the working vs. total plugin stat column
            # to the fmt_str row.
            if settings.plugins:
                plg, ttl_plg = len(data['plugins']), len(TEST_PLUGINS_LIST)

                f_plugins = f'{plg} / {ttl_plg}'
                if plg <= (ttl_plg // 3): f_plugins = f'{Fore.RED}{f_plugins}'
                elif plg <= (ttl_plg // 2): f_plugins = f'{Fore.LIGHTRED_EX}{f_plugins}'
                elif plg < ttl_plg: f_plugins = f'{Fore.YELLOW}{f_plugins}'
                elif plg == ttl_plg: f_plugins = f'{Fore.GREEN}{f_plugins}'

                # fmt_params.append(f'{f_plugins}{Fore.RESET}')
                fmt_str += f'{f_plugins:<15}{Fore.RESET}'
            # print(fmt_str.format(*fmt_params), Fore.RESET)
            print(fmt_str, Fore.RESET)



