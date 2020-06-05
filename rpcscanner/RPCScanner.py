import asyncio
import logging
from asyncio import Task
from collections import namedtuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Tuple, Dict, Coroutine, Union, Awaitable, Optional, Any

import pytz
from colorama import Fore
from dateutil.parser import parse
from privex.helpers import empty, Dictable, DictObject, T, empty_if, convert_datetime, is_true, dec_round
from privex.helpers.types import USE_ORIG_VAR
from rpcscanner.MethodTests import MethodTests, get_filtered_methods
from rpcscanner.settings import TEST_PLUGINS_LIST
from rpcscanner.rpc import rpc, identify_node, RPCBenchType
from rpcscanner.exceptions import ServerDead
from rpcscanner import settings

log = logging.getLogger(__name__)


@dataclass
class NodeStatus(Dictable):
    host: str
    raw: dict
    timing: dict
    tries: dict
    plugins: list = field(default_factory=lambda: [])
    broken_plugins: list = field(default_factory=lambda: [])
    err_reason: str = None
    srvtype: str = 'Unknown'
    current_block: int = None
    block_time: datetime = None
    version: str = None
    network: str = None
    scanned_at: Optional[datetime] = None

    _statuses = {
        0: "Dead",
        1: "Unstable",
        2: "Unreliable",
        3: "Online",
    }

    @property
    def server_type(self) -> str: return self.srvtype

    @property
    def server(self) -> str: return self.host
    
    @property
    def head_block(self) -> int: return self.current_block

    @property
    def ssl(self) -> bool: return 'https://' in self.host

    @property
    def status(self) -> int:
        """Status of the node as a number from 0 to 3"""
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
    def avg_retries(self) -> str:
        """The average amount of RE-tries required per API call to get a valid response, as a 2 DP formatted string"""
        return '{:.2f}'.format(self.total_retries / len(self.tries))
    
    @property
    def plugin_counts(self) -> Tuple[int, int]:
        """Returns as a tuple: how many plugins worked, and how many were tested"""
        return len(self.plugins), len(self.plugins) + len(self.broken_plugins)

    @property
    def time_behind(self) -> Optional[timedelta]:
        if empty(self.block_time): return None
        end = self.scanned_at if self.scanned_at else datetime.utcnow()
        start = convert_datetime(self.block_time).replace(tzinfo=pytz.UTC)
        end = end.replace(tzinfo=pytz.UTC)
        return end - start
    
    @property
    def res_time(self) -> Optional[Decimal]:
        if len(self.timing) > 0:
            time_total = 0.0
            for time_type, time in self.timing.items():
                time_total += time
            avg_res = time_total / len(self.timing)
            return dec_round(Decimal('{:.2f}'.format(avg_res)), dp=2)
        return None
    
    @property
    def api_tests(self) -> str:
        working, total = self.plugin_counts
        return f"{working} / {total}"
    
    def get(self, key: str, fallback=None) -> Any:
        if key in self:
            return getattr(self, key)
        return fallback
    
    def __post_init__(self):
        bt = self.block_time
        if not empty(bt):
            if type(bt) is str and bt.lower() == 'error':
                self.block_time = None
                return
            self.block_time = parse(bt)
    
    def __contains__(self, item):
        return hasattr(self, item)
    
    def __getitem__(self, item):
        try:
            d = getattr(self, item)
            return d
        except AttributeError as e:
            return KeyError(f"re-raised AttributeError after key '{item}' was requested: {type(e)} {str(e)}")
    
    def __str__(self):
        return f'<NodeStatus host="{self.host}" status_human="{self.status_human}" network="{self.network}" ' \
               f'time_behind="{self.time_behind}" api_tests="{self.api_tests}" />'

    def __repr__(self):
        return self.__str__()


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
        p(f'{Fore.GREEN}[Stage 1 / 4] Identifying node types (jussi/appbase){Fore.RESET}')
        for node in self.nodes:
            self.node_status[node] = dict(
                raw={}, timing={}, tries={}, plugins=[],
                current_block='error', block_time='error', version='error',
                srvtype='err', network='err', broken_plugins=[],
                scanned_at=datetime.utcnow().replace(tzinfo=pytz.UTC)
            )
            self.ident_nodes.append((node, self.add_task(identify_node(node))))

        await self.identify_nodes()

        p(f'{Fore.GREEN}[Stage 2 / 4] Filtering out bad nodes{Fore.RESET}')
        await self.filter_badnodes()

        p(f'{Fore.GREEN}[Stage 3 / 4] Obtaining steemd versions {Fore.RESET}')
        await self.scan_versions()

        p(f'{Fore.GREEN}[Stage 4 / 4] Checking current block / block time{Fore.RESET}')
        await self.scan_block_info()

        if settings.plugins:
            p(f'{Fore.GREEN}[Thorough Plugin Check] User specified --plugins. Running thorough plugin tests for alive nodes.{Fore.RESET}')
            pt_list = []

            for host, data in self.node_status.items():
                status = len(data['raw'])
                if status == 0:
                    log.info(f'Skipping node {host} as it appears to be dead.')
                    continue
                log.info(f'{Fore.BLUE} > Running plugin tests for node {host} ...{Fore.RESET}')
                mt = MethodTests(host)
                pt_list += [(host, self.add_task(self.plugin_test(host, plugin, mt))) for plugin in get_filtered_methods()]
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
            log.error(f'{Fore.RED} !!! The API {plugin_name} test failed for node {host}: {type(e)} {str(e)} {Fore.RESET}')
            ns['broken_plugins'].append(plugin_name)

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
                c = await id_data   # type: RPCBenchType
                ident, ident_time, ident_tries = c
                log.info(Fore.GREEN + 'Successfully obtained server type for node %s' + Fore.RESET, host)

                ns['srvtype'] = ident
                ns['timing']['ident'] = ident_time
                ns['tries']['ident'] = ident_tries
                if ns['srvtype'] == 'jussi':
                    log.info(f'Server {host} is JUSSI')
                    meth = 'condenser_api.get_dynamic_global_properties'
                elif ns['srvtype'] == 'appbase':
                    log.info(f'Server {host} is APPBASE (no jussi)')
                    meth = 'condenser_api.get_dynamic_global_properties'
                elif ns['srvtype'] == 'legacy':
                    log.info(f'Server {host} is LEGACY ??? (no jussi)')
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
                c = await blkdata  # type: RPCBenchType
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
                props, props_time, props_tries = await prdata  # type: RPCBenchType
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

    NodeTableRow = namedtuple(
        'NodeTableRow',
        'server server_type ssl status head_block block_time version network res_time avg_retries api_tests',
        defaults=(None,)
    )
    NodeTableColumn = namedtuple('NodeTableColumn', 'title title_padding content_padding', defaults=(25, 25))
    
    # Mapping of NodeTableRow key, to a tuple of (column_title, title_padding, content_padding)
    table_columns: Dict[str, NodeTableColumn] = DictObject(
        server_type=NodeTableColumn('', 5, 15),
        server=NodeTableColumn('Server', 55, 55),
        status=NodeTableColumn('Status', 20, 25),
        head_block=NodeTableColumn('Head Block', 15, 15),
        block_time=NodeTableColumn('Block Time', 25, 25),
        version=NodeTableColumn('Version', 15, 15),
        network=NodeTableColumn('Network', 20, 20),
        res_time=NodeTableColumn('Res Time', 10, 10),
        avg_retries=NodeTableColumn('Avg Retries', 15, 15),
        api_tests=NodeTableColumn('API Tests', 15, 15),
    )
    
    enabled_columns = [
        'server_type', 'server', 'status',
        'head_block', 'block_time', 'version',
        'network', 'res_time', 'avg_retries'
    ]
    
    @classmethod
    def _node_table_row(cls, node: NodeStatus) -> Tuple[str, NodeTableRow]:
        statuses = {
            0: Fore.RED + "DEAD",
            1: Fore.LIGHTRED_EX + "UNSTABLE",
            2: Fore.YELLOW + "Unreliable",
            3: Fore.GREEN + "Online",
        }
        
        # Decide on the node's status based on how many test stages the
        status = statuses[len(node.raw)]
    
        # Calculate the average response time of this node by totalling the timing seconds, and dividing them
        # by the amount of individual timing events
        avg_res = 'error'
        if len(node.timing) > 0:
            time_total = 0.0
            for time_type, time in node.timing.items():
                time_total += time
            avg_res = time_total / len(node.timing)
            avg_res = '{:.2f}'.format(avg_res)
    
        # Calculate the average tries required per successful call by summing up the total amount of tries,
        # and dividing that by the length of the 'tries' dict (individual calls / tests that were tried)
        avg_tries = 'error'
        if len(node['tries']) > 0:
            tries_total = 0
            for tries_type, tries in node.tries.items():
                tries_total += tries
            avg_tries = tries_total / len(node.tries)
            avg_tries = '{:.2f}'.format(avg_tries)
    
        if node.time_behind:
            if node.time_behind.total_seconds() >= 60:
                status = f"{Fore.LIGHTRED_EX}Out-of-sync"
    
        # If there were any moderate errors while testing the node, change the status from green to yellow, and
        # change the status to the error state
        if 'err_reason' in node and not empty(node.err_reason, True, True):
            status = Fore.YELLOW + node.err_reason
        host = str(node.host)
        # Replace the long http:// | https:// URI prefix with a short, clean character in brackets
        host = host.replace('https://', '(S)')
        host = host.replace('http://', '(H)')
    
        # Select the appropriate coloured host type symbol based on the node's detected 'srvtype'
        def_stype = f"{Fore.RED}(?){Fore.RESET}"
        host_stypes = DictObject(
            jussi=f"{Fore.GREEN}(J){Fore.RESET}", appbase=f"{Fore.BLUE}(A){Fore.RESET}", legacy=f"{Fore.MAGENTA}(L){Fore.RESET}"
        )
    
        # If plugin scanning was enabled, generate and append the working vs. total plugin stat column
        # to the fmt_str row.
        f_plugins = ''
        if settings.plugins:
            plg, ttl_plg = len(node.plugins), len(TEST_PLUGINS_LIST)
        
            f_plugins = f'{plg} / {ttl_plg}'
            if plg <= (ttl_plg // 3):
                f_plugins = f'{Fore.RED}{f_plugins}'
            elif plg <= (ttl_plg // 2):
                f_plugins = f'{Fore.LIGHTRED_EX}{f_plugins}'
            elif plg < ttl_plg:
                f_plugins = f'{Fore.YELLOW}{f_plugins}'
            elif plg == ttl_plg:
                f_plugins = f'{Fore.GREEN}{f_plugins}'
            
            f_plugins += Fore.RESET
        
        return node.host, cls.NodeTableRow(
            server=host, server_type=host_stypes.get(node.srvtype, def_stype),
            ssl='https://' in node.host, status=status, head_block=node.current_block,
            block_time=node.block_time, version=node.version, network=node.network, res_time=avg_res,
            avg_retries=avg_tries, api_tests=f_plugins
        )

    table_sort_aliases = dict(
        online='online_status',
        working='online_status',
        dead='dead_status',
        outofsync='outofsync_status',
        plugins='api_tests', apitests='api_tests', tests='api_tests',
        block='head_block',
        time='block_time',
        retries='avg_retries',
        hive='hive_network', steem='steem_network', golos='golos_network', whaleshares='whaleshares_network'
    )
    """We map common alternative names, or shorter names for certain sort_by keys to their real sort_by keys for convenience"""
    
    table_types = dict(
        ssl=bool, block_time=datetime, res_time=Decimal, head_block=int, avg_retries=Decimal, api_tests='len'
    )
    """RPC node columns which shouldn't be casted to a string during sorting are listed in here with their appropriate type"""
    
    table_default_reverse = [
        'api_tests', 'head_block', 'block_time'
    ]
    """
    If a user requests a certain sort key, but doesn't specify whether or not to reverse the table, then this list
    is used to determine which sort keys are best reversed (descending - biggest values first).
    
    Keys not listed in here ( which aren't aliases - see :attr:`.table_sort_aliases` ) will default to the standard
    sorting direction - i.e. ascending - smallest values first
    """
    
    def host_sorter(self, host: str, key: str, fallback=USE_ORIG_VAR) -> Union[str, int, float, bool, datetime, Decimal]:
        """
        Usage::
            
            >>> scanner = RPCScanner(['https://hived.privex.io', 'https://anyx.io', 'https://hived.hive-engine.com'])
            >>> await scanner.scan_nodes()
            >>> sorted(scanner.node_objs, key=lambda el: scanner.host_sorter(host=el.host, key='online_status'))
        
        Useful notes about string sorting:
            
            * ``!`` appears to be the most preferred (comes first when sorting) ASCII character
            
            * ``~`` appears to be the least preferred (comes last when sorting) ASCII character
            
            * Symbols are not linearly grouped together. Some symbols will be sorted first, some will be sorted after numbers,
              some will be sorted after uppercase letters, and some will be sorted after lowercase letters.
            
            * Uppercase and lowercase letters are not grouped together. As per the previous bulletpoint - both uppercase and
              lowercase letters have symbols before + after their preference group.
            
            * The Python string ASCII sorting order seems to be:
                * Certain common symbols such as exclamation ``!``, quote ``"``, hash ``#``, dollar ``$`` and others
                * Numbers ``0`` to ``9``
                * Less common symbols such as colon ``:``, semi-colon ``;``, lessthan ``<``, equals ``=`` and greaterthan ``=`` (and more)
                * Uppercase alphabet characters ``A`` to ``Z``
                * Even less common symbols such as open square bracket ``[``, backslash ``\``, close square bracket ``]`` and others.
                * Lowercase alphabet characters ``a`` to ``z``
                * Rarer symbols such as curly braces ``{`` ``}``, pipe ``|``, tilde ``~`` and more.
        
        The tilde '~' character appears to be one of the least favorable string characters, coming in last
        place when I did some basic testing in the REPL on Python 3.8, with the following character set (sorted)::
        
            >>> x = list('!"#$%&\\'()*+,-./0123456789:;<=>?@ABC[\\]^_`abc{|}~')
            >>> x = list(set(x))   # Remove any potential duplicate characters
        
        Tested with::
        
            >>> print(''.join(sorted(list(set(x)), key=lambda el: str(el))))
            !"#$%&'()*+,-./0123456789:;<=>?@ABC[\\]^_`abc{|}~
        
        Note: extra backslashes have been added to the character set example above, due to IDEs thinking it's an escape
        for the docs - and thus complaining.
        
        :param str host: The host being sorted, e.g. ``https://hived.privex.io``
        :param str key: The key being sorted / special sort code, e.g. ``head_block`` or ``online_status``
        :param fallback:
        :return:
        """
        node = self.get_node(host)
        key = self.table_sort_aliases.get(key, key)
        real_key = str(key)
        if key in ['api_tests', 'plugins']:
            if empty(node.plugins, True, True): return 0
            return len(node.plugins) / len(TEST_PLUGINS_LIST)
        if '_status' in key:
            content = node.status + 1
            # When sorting by a specific status key, we handle out-of-sync nodes by simply emitting
            # status 0 (best) if we're prioritising out-of-sync nodes, or status 2 (unreliable) when
            # sorting by any other status.
            if node.time_behind:
                if node.time_behind.total_seconds() > 60:
                    return 0 if key == 'outofsync_status' else 2
            if key == 'online_status' and node.status >= 3:
                return 0
            if key == 'dead_status'and node.status <= 0:
                return 0
            if key == 'outofsync_status': pass
            return content

        if key.endswith('_network'):
            real_key = 'network'
        
        if real_key not in node:
            log.error(f"RPCScanner.host_sorter called with non-existent key '{key}'. Falling back to sorting by 'status'.")
            key, real_key = 'status', 'status'
        
        content = node.get(real_key, '')
        strcont = str(content)
        has_err = 'error' in strcont.lower() or 'none' in strcont.lower()
        def_reverse = real_key in self.table_default_reverse
        log.debug(f"Key: {key} || Real Key: {real_key} has_err: {has_err} || def_reverse: {def_reverse} "
                  f"|| content: {content} || strcont: {strcont}")
        # If a specific network sort type is given, then return '!' if this node matches that network.
        # The exclamation mark symbol '!' is very high ranking with python string sorts (higher than numbers and letters)
        if key == "hive_network": return '!' if 'hive' in strcont.lower() else strcont
        if key == "steem_network": return '!' if 'steem' in strcont.lower() else strcont
        if key == "whaleshares_network": return '!' if 'whaleshares' in strcont.lower() else strcont
        if key == "golos_network": return '!' if 'golos' in strcont.lower() else strcont
        
        # If 'table_types' tells us that the column we're sorting by - should be handled as a certain type,
        # then we need to change how we handle the default fallback value for errors, and any casting
        # we should use.
        if key in self.table_types:
            tt = self.table_types[key]
            log.info(f"Key {key} has table type: {tt}")
            if tt is bool:
                if has_err or empty(content): return False if def_reverse else True
                return is_true(content)
            if tt is datetime:
                fallback = (datetime.utcnow() + timedelta(weeks=260, hours=12)).replace(tzinfo=pytz.UTC)
                if def_reverse: fallback = datetime(1980, 1, 1, 1, 1, 1, 1, tzinfo=pytz.UTC)
                if has_err or empty(content): return fallback
                return convert_datetime(content, if_empty=fallback)
            if tt is float:
                if has_err and isinstance(fallback, float): return fallback
                if has_err or empty(content): return float(0.0) if def_reverse else float(999999999.99999)
                return float(content)
            if tt is Decimal:
                if has_err and isinstance(fallback, Decimal): return fallback
                if has_err or empty(content): return Decimal('0') if def_reverse else Decimal('999999999')
                return Decimal(content)
            if tt is int:
                if has_err and isinstance(fallback, int): return fallback
                if has_err or empty(content): return int(0) if def_reverse else int(999999999)
                return int(content)

        if has_err or empty(content):
            # We use the placeholder type 'USE_ORIG_VAR' instead of 'None' or 'False', allowing us the user to specify
            # 'None', 'False', '""' etc. as fallbacks without conflict
            if fallback is not USE_ORIG_VAR: return fallback
            # The '!' character is used as the default fallback value if the table is reversed by default,
            # since '!' appears to be the most preferred string character, and thus would be at the
            # bottom of a reversed list.
            if def_reverse: return '!'
            # The tilde '~' character appears to be one of the least favorable string characters, coming in last
            # place when I did some basic testing in the REPL on Python 3.8 (see pydoc block for this method),
            # so it's used as the default for ``fallback``.
            return '~'
        # If we don't have a known type for this column, or any special handling needed like for 'api_tests', then we
        # simply return the stringified content of the key on the node object.
        return strcont
    
    def prepare_table(self, sort_by='default', reverse: Optional[bool] = None) -> List[Tuple[str, NodeTableRow]]:
        ntable = [
            self._node_table_row(node) for node in self.node_objs
        ]   # type: List[Tuple[str, RPCScanner.NodeTableRow]]
        
        real_key = self.table_sort_aliases.get(sort_by, sort_by)
        if reverse is None:
            reverse = real_key in self.table_default_reverse
        if empty(sort_by) or sort_by == 'default':
            return list(reversed(ntable)) if reverse else ntable
        
        return sorted(ntable, key=lambda el: self.host_sorter(el[0], key=sort_by), reverse=reverse)

    def _render_node_row(self, row: Optional[NodeTableRow] = None, columns: list = None) -> str:
        columns = empty_if(columns, self.table_columns.keys(), itr=True)
        r = ''
        
        for c in columns:
            col_obj = self.table_columns[c]
            data, padding = col_obj.title, col_obj.title_padding
            if row:
                data, padding = getattr(row, c), col_obj.content_padding
            
            r += ("{:<" + str(padding) + "}").format(str(data))
        
        return r

    def print_nodes(self, sort_by='default', reverse: Optional[bool] = None):
        """
        Pretty print the node status information from :attr:`.node_status` in a colour coded table, with cleanly
        padded columns for easy readability.
        """
        cols = list(self.enabled_columns)
        if settings.plugins:
            cols += ['api_tests']
        
        rows = [self._render_node_row(columns=cols)]
        rows += [self._render_node_row(row) for _, row in self.prepare_table(sort_by=sort_by, reverse=reverse)]
        print(Fore.BLUE, '(S) - SSL, (H) - HTTP : (A) - appbase (J) - jussi (L) - legacy', Fore.RESET)
        print(Fore.BLUE, end='', sep='')
        for row in rows:
            print(row)
        print(Fore.RESET)



