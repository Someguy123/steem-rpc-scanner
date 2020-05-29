#!/usr/bin/env python3
"""
Steem node RPC scanner
    by @someguy123

Version 1.4

Python 3.7.0 or higher recommended

"""
import dotenv
dotenv.load_dotenv()

import asyncio
from privex.helpers import ErrHelpParser
from rpcscanner import RPCScanner, settings, load_nodes, set_logging_level
import logging
import signal

log = logging.getLogger('rpcscanner.app')


parser = ErrHelpParser(description='Scan RPC nodes from a list of URLs to determine their last block, '
                                   'version, reliability, and response time.')
parser.add_argument('-v', dest='verbose', action='store_true', help='display debugging')
parser.add_argument('-q', dest='quiet', action='store_true', help='only show warnings or worse')
parser.add_argument('-f', dest='nodefile', help=f'specify a custom file to read nodes from (default: {settings.node_file})')
parser.add_argument('--account', dest='account', help='Steem username used for tests requiring an account to lookup')
parser.add_argument('--plugins', action='store_true', dest='plugins', help='Run thorough plugin testing after basic filter tests complete.')
parser.set_defaults(
    verbose=settings.verbose, quiet=settings.quiet, plugins=settings.plugins,
    account=settings.test_account, nodefile=settings.node_file
)
args = parser.parse_args()

# Copy values of command line args into the application's settings.
settings.verbose, settings.quiet, settings.plugins = args.verbose, args.quiet, args.plugins
settings.node_file, settings.test_account = args.nodefile, args.account

debug_level = logging.INFO

if settings.quiet:
    debug_level = logging.CRITICAL
elif settings.verbose:
    print('Verbose mode enabled.')
    debug_level = logging.DEBUG
else:
    print("For more verbose logging (such as detailed scanning actions), use `./app.py -v`")
    print("For less output, use -q for quiet mode (display only critical errors)")

set_logging_level(debug_level)


async def scan():
    node_list = load_nodes(settings.node_file)
    rs = RPCScanner(nodes=node_list)
    await rs.scan_nodes()
    rs.print_nodes()


if __name__ == "__main__":
    # Make CTRL-C work properly with Twisted's Reactor / AsyncIO
    # https://stackoverflow.com/a/4126412/2648583
    signal.signal(signal.SIGINT, signal.default_int_handler)
    asyncio.run(scan())

