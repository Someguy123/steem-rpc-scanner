#!/usr/bin/env python3
"""
Hive/Steem/other RPC node scanner
    by @someguy123

Version 2.1

Python 3.8.0 or higher is strongly recommended, however it may work on 3.7+

"""
import argparse
import sys
import asyncio
import textwrap

from privex.helpers import ErrHelpParser
from rpcscanner import RPCScanner, settings, load_nodes, arguments
import logging
import signal

log = logging.getLogger('rpcscanner.app')

desc_def_reversed = "\n        - ".join(RPCScanner.table_default_reverse)
desc_sort_aliases = ''
_alias_line, _tmp_alias_lines = '', []
for alias, orig_name in RPCScanner.table_sort_aliases.items():
    l = f"{alias} ({orig_name}), "
    if (len(_alias_line) + len(l)) > 90:
        _tmp_alias_lines.append(_alias_line)
        _alias_line = ''
    _alias_line += l
if len(_alias_line) > 0: _tmp_alias_lines.append(_alias_line)
desc_sort_aliases = f"\n        ".join(_tmp_alias_lines).strip(', ')

desc = textwrap.dedent(f"""

    Someguy123's Hive / Steem-based RPC Scanner tool
    (C) 2020 Someguy123 ( https://peakd.com/@someguy123 ) / Privex Inc. ( https://wwww.privex.io )
    
    Source Code: https://github.com/Someguy123/steem-rpc-scanner
    License: GNU AGPL 3.0

    app.py - Mass RPC List Scanner with colour coded output

    Scan RPC nodes from a list of URLs to determine their last block, version, reliability,
    and response time.
    
    For more targeted usage, use health.py - see './health.py -h'. The health.py script contains various
    sub-commands which can be used to programmatically by interpreting their exit code, or parsing their
    standard output format.
    
    Sorting options:
    
        - server            - Sort by server URL
        - status            - Sort by server status
            - online        - Sort by server status (preferring 'Online' nodes the most)
            - dead          - Sort by server status (preferring 'DEAD' nodes the most)
            - outofsync     - Sort by server status (preferring 'Out-of-sync' nodes the most)
        - head_block        - Sort by server's last block number
        - block_time        - Sort by server's last block time
        - version           - Sort by server's version number
        - network           - Sort by server's network
            - hive          - Sort by server's network (preferring 'Hive' the most)
            - steem         - Sort by server's network (preferring 'Steem' the most)
            - golos         - Sort by server's network (preferring 'Golos' the most)
            - whaleshares   - Sort by server's network (preferring 'Whaleshares' the most)
        - res_time          - Sort by server's average response time
        - avg_retries       - Sort by server's average retries
        - api_tests         - Sort by amount of API tests passed (requires '--plugins')
    
    The following sorting options are **reversed by default** for convenience, as higher numbers indicate
    better health for these health stats (--reverse will thus sort these **forwards**):
    
        - {desc_def_reversed}
    
    For your convenience, there are also many aliases for different sorting options:
        
        {desc_sort_aliases}
    
    This should help reduce the need for you to constantly check the help page to remember what the name was
    for a certain sorting option was :)
    
""")

parser = ErrHelpParser(
    description="Someguy123's Hive / Steem-based RPC Scanner tool",
    epilog=desc, formatter_class=argparse.RawDescriptionHelpFormatter
)
parser.add_argument('--account', dest='account', help='Hive/Steem username used for tests requiring an account to lookup')
parser.add_argument('-s', '--sort', '--order', dest='order', help="Sort nodes by this column / sorting method (see help)")
parser.add_argument('-r', '--reverse', '--invert', dest='reverse', action='store_true', default=False, help="Reverse the sorting order")
arguments.add_arguments(parser, 'verbose', 'quiet', 'plugins', 'skip_apis', 'nodefile')
arguments.add_defaults(parser, account=settings.test_account, order='default', reverse=False)
args = parser.parse_args()

arguments.handle_args(args)

settings.test_account = args.account

debug_level = logging.INFO

if not settings.quiet and not settings.verbose:
    print("For more verbose logging (such as detailed scanning actions), use `./app.py -v`", file=sys.stderr)
    print("For less output, use -q for quiet mode (display only critical errors)", file=sys.stderr)


async def scan(opts: argparse.Namespace):
    node_list = load_nodes(settings.node_file)
    rs = RPCScanner(nodes=node_list)
    rev = None if not opts.reverse else opts.reverse
    order = opts.order
    if rev and order in rs.table_default_reverse:
        rev = False
    await rs.scan_nodes()
    rs.print_nodes(sort_by=order, reverse=rev)


if __name__ == "__main__":
    # Make CTRL-C work properly with Twisted's Reactor / AsyncIO
    # https://stackoverflow.com/a/4126412/2648583
    signal.signal(signal.SIGINT, signal.default_int_handler)
    asyncio.run(scan(args))

