#!/usr/bin/env python3
"""
Health check script - test individual nodes, with system return codes based on status.

Designed for use in bash scripts
"""
import dotenv
dotenv.load_dotenv()

import argparse
import asyncio
import logging
import sys
import textwrap
import signal
from datetime import datetime
from typing import Tuple

from privex.helpers import ErrHelpParser, empty

from rpcscanner import load_nodes, settings, RPCScanner, set_logging_level, clear_handlers
from rpcscanner.RPCScanner import NodeStatus, TOTAL_STAGES_TRACKED

MAX_SCORE = 50
# How many normal tries are there?
BASE_TRIES = 3
settings.plugins = True
# settings.quiet = True

help_text = textwrap.dedent('''\

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

parser = ErrHelpParser(
    description="Someguy123's Steem Node Health Checker",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=help_text
)

parser.add_argument('-s', dest='min_score', type=int, default=MAX_SCORE - 10,
                    help=f'Minimum score required before assuming a node is good (1 to {MAX_SCORE})')

parser.add_argument('-q', '--quiet', dest='quiet', action='store_true', default=settings.quiet,
                    help=f'Quiet logging mode')

parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=False,
                    help=f'Verbose logging mode')

parser.set_defaults(verbose=settings.verbose, quiet=settings.quiet)

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


p_scan = subparser.add_parser('scan', description='Scan an individual node')
p_scan.set_defaults(func=scan)
p_scan.add_argument('node', help='Steem Node with http(s):// prefix')


p_list = subparser.add_parser('list', description='Scan and output a plain text list of working nodes')
p_list.add_argument('-d', dest='detailed', action='store_true', default=False,
                    help='Return whitespace separated status information after the nodes in the list.')
p_list.set_defaults(func=list_nodes, detailed=False)

args = parser.parse_args()

if args.quiet:
    settings.quiet = True
    settings.verbose = False
    clear_handlers('rpcscanner', None)
    set_logging_level(logging.CRITICAL, None)
elif args.verbose:
    settings.quiet = False
    settings.verbose = True
    clear_handlers('rpcscanner', None)
    set_logging_level(logging.DEBUG, None)


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
    print(f"""
Node: {node}
Status: {status_name}
Network: {n.network}
Version: {n.version}
Block: {n.current_block}
Time: {dt} ({time_behind} ago)
Plugins: {plug_tried} / {plug_total}
PluginList: {n.plugins}
PassedStages: {n.status} / {TOTAL_STAGES_TRACKED}
Retries: {n.total_retries}
Score: {score} (out of {MAX_SCORE})
""")
    return sys.exit(return_code)


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
    if plug_tried < plug_total: score -= (plug_total - plug_tried) * 4
    
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

# parser.add_argument('node', help='')
