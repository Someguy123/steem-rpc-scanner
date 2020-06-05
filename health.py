#!/usr/bin/env python3
"""
Health check script - test individual nodes, with system return codes based on status.

Designed for use in bash scripts
"""
import argparse
import asyncio
import json
import logging
import sys
import textwrap
import signal
from colorama import Fore
from datetime import datetime
from typing import Tuple, Union, Dict
from privex.helpers import ErrHelpParser, empty, DictObject, empty_if
from rpcscanner import load_nodes, settings, RPCScanner, MethodTests, get_supported_methods, \
    RPCError, ServerDead
from rpcscanner.rpc import rpc
from rpcscanner.settings import MAX_SCORE
from rpcscanner import arguments, get_filtered_methods
from rpcscanner.RPCScanner import NodeStatus, TOTAL_STAGES_TRACKED

log = logging.getLogger('rpcscanner.health_cli')


# How many normal tries are there?
BASE_TRIES = 3
settings.plugins = True
# settings.quiet = True

help_text = textwrap.dedent('''\

    Someguy123's Hive / Steem-based RPC Scanner tool
    (C) 2020 Someguy123 ( https://peakd.com/@someguy123 ) / Privex Inc. ( https://wwww.privex.io )
    
    Source Code: https://github.com/Someguy123/steem-rpc-scanner
    License: GNU AGPL 3.0
    
    For more user friendly / human readable output, use app.py - see './app.py -h'. The app.py script
    is designed to simply scan ``nodes.conf`` (or an alternative file specified via ``NODE_FILE`` or ``-f``),
    and output the results in a colour coded, tabular format, designed for human readability.

    This health check script has two modes:

        scan  [node]    - Scan an individual node, and return exit 0 if it's working, or 1 if it's not.
        list  [-d]      - Return a list of working nodes from nodes.txt (-d returns more detailed status info, 
                          which is whitespace separated)    
        
    Examples:
    
        Scan Privex's RPC node, which will return 0 or 1, and output a small message detailing the status.
        
            $ ./health.py scan "https://direct.steemd.privex.io"
            Node: https://direct.steemd.privex.io
            Status: GOOD
            Version: 0.20.11
            Block: 34343750
            Time: 2019-07-03T17:01:24
            Plugins: 4 / 4
        
        Scan all nodes in nodes.txt and output the working ones in a plain list.
        
            $ ./health.py list
            https://direct.steemd.privex.io
            https://api.steemit.com
        
        Scan all nodes in nodes.txt and output the working ones in a plain list, with details sep by whitepsace.
        
            $ ./health.py list
            Node Status Score Version Block Time Plugins
            https://direct.steemd.privex.io GOOD 20 0.20.11 34343750 2019-07-03T17:01:24 4/4
            https://api.steemit.com GOOD 18 0.20.11 34343750 2019-07-03T17:01:24 4/4

''')

no_plugins_help = f'Do NOT test individual plugin APIs when scanning RPC nodes. This will speed up scanning, but '\
                  f'will give less accurate test results as only very basic API tests will be done. NOTE: When plugin '\
                  f'scanning is disabled, scores still go up to {MAX_SCORE}, but node scores will not be degraded '\
                  f'by plugin test results.'

parser = ErrHelpParser(
    description="Someguy123's Hive/Steem RPC Node Health Checker",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=help_text
)

parser.add_argument('-s', dest='min_score', type=int, default=MAX_SCORE - 10,
                    help=f'Minimum score required before assuming a node is good (1 to {MAX_SCORE})')

arguments.add_arguments(parser, 'verbose', 'quiet', 'nodefile')

parser.set_defaults()

subparser = parser.add_subparsers()


def scan(opt):
    if 1 > opt.min_score > MAX_SCORE:
        return parser.error(f'Minimum score must be between 1 and {MAX_SCORE}')
    # Make CTRL-C work properly with Twisted's Reactor
    # https://stackoverflow.com/a/4126412/2648583
    signal.signal(signal.SIGINT, signal.default_int_handler)
    asyncio.run(_scan(opt.node, opt.min_score))


def list_nodes(opt):
    if 1 > opt.min_score > MAX_SCORE:
        return parser.error(f'Minimum score must be between 1 and {MAX_SCORE}')
    # Make CTRL-C work properly with Twisted's Reactor
    # https://stackoverflow.com/a/4126412/2648583
    signal.signal(signal.SIGINT, signal.default_int_handler)
    asyncio.run(_list_nodes(opt.detailed, opt.min_score))
    # react(_list_nodes, (opt.detailed, opt.min_score,))


def test_method(opt):
    meth = opt.method.lower()
    node = opt.node
    params = opt.params
    print('====================================================================================', file=sys.stderr)
    print(f'# {Fore.CYAN}Testing Node: {node}       {Fore.MAGENTA}API Method: {meth}{Fore.RESET}\n', file=sys.stderr)
    loop = asyncio.get_event_loop()
    res = loop.run_until_complete(_test_methods(node, meth, params=params, auto_exit=False))
    status = res.methods[meth]

    if status:
        print(f"{meth:<50} {Fore.GREEN}WORKING{Fore.RESET}\n")
        return sys.exit(settings.GOOD_RETURN_CODE)
    print(f"{meth:<50} {Fore.RED}BROKEN{Fore.RESET}\n")
    return sys.exit(settings.BAD_RETURN_CODE)


def test_methods(opt):
    print('====================================================================================', file=sys.stderr)
    print(f'# {Fore.CYAN}Testing Node: {Fore.BLUE}{opt.node}{Fore.RESET}', file=sys.stderr)
    print(f'# {Fore.MAGENTA}API Methods: {Fore.YELLOW}{opt.methods}{Fore.RESET}', file=sys.stderr)
    print('------------------------------------------------------------------------------------', file=sys.stderr)
    # try:
    loop = asyncio.get_event_loop()
    res = loop.run_until_complete(_test_methods(opt.node, *opt.methods, params=opt.params, auto_exit=False))

    total_methods, working, broken = len(list(opt.methods)), 0, 0
    if 'min_methods' in args and not empty(args.min_methods):
        min_meths = args.min_methods
    else:
        min_meths = 1 if int(total_methods * 0.75) < 1 else int(total_methods * 0.75)
    for meth, status in res.methods.items():
        if status:
            print(f"{meth:<50} {Fore.GREEN}WORKING{Fore.RESET}")
            working += 1
        else:
            print(f"{meth:<50} {Fore.RED}BROKEN{Fore.RESET}")
            broken += 1

    print('------------------------------------------------------------------------------------', file=sys.stderr)
    print(f"# {Fore.CYAN}WORKING | BROKEN | TOTAL: {Fore.GREEN}{working}{Fore.RESET} | "
          f"{Fore.RED}{broken}{Fore.RESET} | {Fore.MAGENTA}{total_methods}{Fore.RESET}")
    
    if working < min_meths: zstatus = f"{Fore.RED}BAD"
    elif working == total_methods: zstatus = f"{Fore.GREEN}PERFECT"
    else: zstatus = f"{Fore.LIGHTGREEN_EX}GOOD"
    print(f"# {Fore.BLUE}Overall status: {zstatus}{Fore.RESET}")
    print(f"# {Fore.MAGENTA}Min working methods for GOOD status: {Fore.LIGHTGREEN_EX}{min_meths}{Fore.RESET}")

    print('\n====================================================================================', file=sys.stderr)
    print()

    if working < min_meths:
        return sys.exit(settings.BAD_RETURN_CODE)
    return sys.exit(settings.GOOD_RETURN_CODE)


# -------------------------------------------------- scan ------------------------------------------------
p_scan = subparser.add_parser('scan', description='Scan an individual node')
p_scan.set_defaults(func=scan)
arguments.add_arguments(p_scan, 'no_plugins', 'skip_apis', 'node')

# -------------------------------------------------- list ------------------------------------------------
p_list = subparser.add_parser('list', description='Scan and output a plain text list of working nodes')
p_list.add_argument('-d', dest='detailed', action='store_true', default=False,
                    help='Return whitespace separated status information after the nodes in the list.')
arguments.add_arguments(p_list, 'no_plugins', 'skip_apis', 'nodefile')

p_list.set_defaults(func=list_nodes)

arguments.add_defaults(parser, detailed=False)

# --------------------------------------------- test_methods ---------------------------------------------
_sup_meths = f"Supported methods: {', '.join(get_filtered_methods())}"

p_test_methods = subparser.add_parser(
    'test_methods', description="Test multiple API methods an RPC node (only method testing, no identification / basic scanning). "
                                "If no methods are specified via positional args, all supported methods will be tested."
)
arguments.add_arguments(p_test_methods, 'params', 'node')
p_test_methods.add_argument(
    'methods', nargs='*', default=get_filtered_methods(),
    help=f"One or more API methods to test (e.g. \"condenser_api.get_blog\") as positional args. If no methods are specified via "
         f"positional args, all supported methods will be tested. {_sup_meths}",
)
p_test_methods.add_argument(
    '-l', '--min-methods', dest='min_methods', type=int, default=None,
    help=f'Minimum number of working methods before assuming a node is good (status code zero). Default: 75%% of tested methods.'
)
p_test_methods.set_defaults(func=test_methods)

# --------------------------------------------- test_method ---------------------------------------------
p_test_method = subparser.add_parser(
    'test_method', description="Test an individual API method against an RPC node (No other scanning e.g. identification)"
)
arguments.add_arguments(p_test_method, 'params', 'node')
p_test_method.add_argument(
    'method', help=f"The API method to test (e.g. \"condenser_api.get_blog\") as a positional arg. {_sup_meths}",
)
p_test_method.set_defaults(func=test_method)

args = parser.parse_args()

arguments.handle_args(args)


def iso_timestr(dt: datetime) -> str:
    """Convert datetime object into ISO friendly ``2010-03-03Z21:16:45``"""
    return str(dt.isoformat()).split('.')[0]


async def _list_nodes(detailed, min_score):
    node_list = load_nodes(settings.node_file)
    rs = RPCScanner(nodes=node_list)
    await rs.scan_nodes(True)

    if detailed:
        print('(Detailed Mode. This msg and row header are sent to stderr for easy removal)', file=sys.stderr)
        print('Node                          Status         Score     Version   Block          Time           Plugins', file=sys.stderr)
    for n in rs.node_objs:
        score, _, status_name = score_node(min_score, n)
        if score < min_score:
            continue

        if detailed:
            p_tr, p_tot = n.plugin_counts
            dt = iso_timestr(n.block_time) if not empty(n.block_time) else 'Unknown'
            print(f'{n.host:<30} {status_name:<15} {score:<10} {n.version:<10} {n.current_block:<15} {dt:<15} {p_tr}/{p_tot} ')
            continue
        print(n.host)


async def _scan(node, min_score):
    rs = RPCScanner(nodes=[node])
    await rs.scan_nodes(True)

    n = rs.get_node(node)
    plug_tried, plug_total = n.plugin_counts

    score, return_code, status_name = score_node(min_score, n)

    if score == 0:
        print("Node: {}\nStatus: DEAD".format(node))
        return sys.exit(1)
    dt = iso_timestr(n.block_time) if not empty(n.block_time) else 'Unknown'
    time_behind = "N/A"
    if n.time_behind:
        time_behind = str(n.time_behind).split('.')[0]
    out = f"""
Node: {node}
Status: {status_name}
Network: {n.network}
Version: {n.version}
Block: {n.current_block}
Time: {dt} ({time_behind} ago)
"""
    if settings.plugins:
        out += f"Plugins: {plug_tried} / {plug_total}\nPluginList: {n.plugins}\nBrokenAPIs: {n.broken_plugins}\n"
    out += f"""PassedStages: {n.status} / {TOTAL_STAGES_TRACKED}
Retries: {n.total_retries}
Score: {score} (out of {MAX_SCORE})
"""
    print(out)
    return sys.exit(return_code)


async def _try_unknown_method(node: str, method: str, params: Union[list, dict] = None, auto_exit=True):
    params = empty_if(params, [])
    try:
        # loop = asyncio.get_event_loop()
        data = await rpc(host=node, method=method, params=params)
        if empty(data[0]):
            log.warning("Response for method '%s' from '%s' was empty. Marking as broken!", method, node)
            return sys.exit(settings.BAD_RETURN_CODE) if auto_exit else False
        return data
    except RPCError as e:
        log.error("Got RPC error in _try_unknown_method() while testing method %s against %s - Ex: %s %s", method, node, type(e), str(e))
        return sys.exit(settings.BAD_RETURN_CODE) if auto_exit else False
    except ServerDead as e:
        log.error(
            "Got ServerDead error in _try_unknown_method() while testing method %s against %s - Ex: %s %s", method, node, type(e), str(e)
        )
        oe = e.orig_ex
        if not empty(oe):
            if isinstance(oe, RPCError):
                log.error("ServerDead contained RPCError while testing method %s against %s - Ex: %s %s", method, node, type(oe), str(oe))
        return sys.exit(settings.BAD_RETURN_CODE) if auto_exit else False
    except Exception as e:
        log.error("Fatal exception in _try_unknown_method() while testing method %s against %s - Ex: %s %s", method, node, type(e), str(e))
        return sys.exit(1) if auto_exit else False


async def _test_methods(node: str, *methods: str, params='[]', auto_exit=True) -> Union[DictObject, Dict[str, dict]]:
    # mt = MethodTests(node)
    # loop = asyncio.get_event_loop()
    sup_methods = [meth for meth in methods if meth in get_supported_methods()]
    unsup_methods = [meth for meth in methods if meth not in get_supported_methods()]
    if len(unsup_methods) > 0:
        log.error(
            f"CAUTION: The RPC API method(s) '{unsup_methods}' are not supported yet. This means a proper, thorough, example "
            f"request + response test - has NOT been created for these method(s). Despite this, we'll try querying '{node}' "
            f"using the unsupported method(s) using the parameters '{params}', and checking for a non-empty 'result' key in the response."
        )
        log.error("You can use the CLI argument '--params' to change the parameters used for unsupported RPC methods.")

    res = DictObject(methods={}, errors={}, results={})
    if len(sup_methods) > 0:
        res = await MethodTests(node).test_all(whitelist=list(sup_methods))
    
    if not empty(params):
        params = json.loads(params)
    else:
        params = []
    
    for m in unsup_methods:
        ures = await _try_unknown_method(node=node, method=m, params=params, auto_exit=auto_exit)
        if ures is False:
            res.methods[m] = False
            res.errors[m] = "unknown error"
            continue
        res.methods[m] = True
        res.results[m] = ures[0]
        
    # return loop.run_until_complete(MethodTests(node).test_all(whitelist=list(methods)))
    return res


def score_node(min_score: int, n: NodeStatus) -> Tuple[int, int, str]:
    """
    Reviews the status information from a :py:class:`NodeStatus` object, and returns a numeric score, return code,
    and human friendly status description as a tuple.

    Usage:

    >>> node = 'https://steemd.privex.io'
    >>> rs = RPCScanner(reactor, nodes=[node])
    >>> n = rs.get_node(node)
    >>> score, return_code, status_name = score_node(15, n)
    >>> print(score, return_code, status_name)
    18 0 GOOD

    :param  int     min_score: Minimum score before a node is deemed "bad"
    :param  NodeStatus      n: The NodeStatus object to use for scoring
    :return tuple  statusinfo: (score:int, return_code:int, status_name:str)
    """
    # A node scores points based on whether it appears to be up, how many tries it took, and how many plugins work.
    score, status = 0, n.status
    plug_tried, plug_total = n.plugin_counts

    # If a node has a status of "dead", it immediately scores zero points and returns a bad status.
    if status <= 0:
        return 0, 1, 'DEAD'
    elif status == 1:   # Unstable nodes lose 10 points
        score += MAX_SCORE - 10
    elif status == 2:  # Unreliable nodes lose 5 points
        score += MAX_SCORE - 5
    elif status >= 3:   # Stable nodes start with full points
        score += MAX_SCORE

    # Nodes lose two score points for every retry needed
    if n.total_retries > 0: score -= (n.total_retries * 2)
    
    # Nodes lose 4 points for each plugin that's responding incorrectly
    if settings.plugins and plug_tried < plug_total: score -= (plug_total - plug_tried) * 4
    
    # Out-of-sync nodes lose between 5% and 80% of the max score depending on how far behind they are
    if n.time_behind:
        pre_score = int(score)
        if n.time_behind.total_seconds() > 86400: score -= int(MAX_SCORE * 0.8)
        elif n.time_behind.total_seconds() > 3600: score -= int(MAX_SCORE * 0.5)
        elif n.time_behind.total_seconds() > 600: score -= int(MAX_SCORE * 0.3)
        elif n.time_behind.total_seconds() > 300: score -= int(MAX_SCORE * 0.15)
        elif n.time_behind.total_seconds() > 60: score -= int(MAX_SCORE * 0.10)
        elif n.time_behind.total_seconds() > 30: score -= int(MAX_SCORE * 0.05)
        # If the node we're scoring was brought below a 10% score due to these time penalties, then we check it's score prior
        # to the time penalty, and boost the score up to as high as 20%, depending on how well the node previously scored.
        # This ensures that nodes which are functional, but just severely out of sync, aren't marked as completely dead.
        if score < int(MAX_SCORE * 0.1):
            if pre_score > int(MAX_SCORE * 0.8): score = int(MAX_SCORE * 0.2)
            if pre_score > int(MAX_SCORE * 0.5): score = int(MAX_SCORE * 0.1)
            if pre_score > int(MAX_SCORE * 0.2): score = int(MAX_SCORE * 0.05)

    score = int(score)
    score = 0 if score < 0 else score
    return_code = settings.BAD_RETURN_CODE if score < min_score else settings.GOOD_RETURN_CODE
    status_name = 'BAD' if score < min_score else 'GOOD'
    status_name = 'PERFECT' if score >= MAX_SCORE else status_name
    return score, return_code, status_name


if __name__ == "__main__":
    # Resolves the error "'Namespace' object has no attribute 'func'
    # Taken from https://stackoverflow.com/a/54161510/2648583
    try:
        func = args.func
        func(args)
    except AttributeError:
        parser.error('Too few arguments')

