#!/usr/bin/env python3
"""
Steem node RPC scanner
    by @someguy123

Version 1.4

Python 3.7.0 or higher recommended

"""

from twisted.internet.defer import inlineCallbacks
from twisted.internet.task import react
from privex.loghelper import LogHelper
from privex.helpers import ErrHelpParser
from rpcscanner import RPCScanner, settings
import logging
import signal

parser = ErrHelpParser(description='Scan RPC nodes from a list of URLs to determine their last block, '
                                   'version, reliability, and response time.')
parser.add_argument('-v', dest='verbose', action='store_true', default=False, help='display debugging')
parser.add_argument('-q', dest='quiet', action='store_true', default=False, help='only show warnings or worse')
parser.add_argument('-f', dest='nodefile', default='nodes.txt',
                    help='specify a custom file to read nodes from (default: nodes.txt)')
parser.add_argument('--account', dest='account', default='someguy123',
                    help='Steem username used for tests requiring an account to lookup')
parser.add_argument('--plugins', action='store_true', dest='plugins', default=False,
                    help='Run thorough plugin testing after basic filter tests complete.')
parser.set_defaults(verbose=False, quiet=False, plugins=False, account='someguy123')
args = parser.parse_args()

# Copy values of command line args into the application's settings.
settings.verbose, settings.quiet, settings.plugins = args.verbose, args.quiet, args.plugins
settings.node_file, settings.test_account = args.nodefile, args.account

debug_level = logging.INFO

if settings.verbose:
    print('Verbose mode enabled.')
    debug_level = logging.DEBUG
elif settings.quiet:
    debug_level = logging.WARNING
else:
    print("For more verbose logging (such as detailed scanning actions), use `./app.py -v`")
    print("For less output, use -q for quiet mode (display only warnings and errors)")

f = logging.Formatter('[%(asctime)s]: %(funcName)-18s : %(levelname)-8s:: %(message)s')
lh = LogHelper(handler_level=debug_level, formatter=f)
lh.add_console_handler()
log = lh.get_logger()

# s = requests.Session()


@inlineCallbacks
def scan(reactor):
    rs = RPCScanner(reactor)
    yield from rs.scan_nodes()


if __name__ == "__main__":
    # Make CTRL-C work properly with Twisted's Reactor
    # https://stackoverflow.com/a/4126412/2648583
    signal.signal(signal.SIGINT, signal.default_int_handler)
    react(scan)
