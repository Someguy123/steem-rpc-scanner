"""
The settings in this file will normally be overwritten by the CLI tool, from either
a .env file, or arguments passed on the CLI.
"""
import logging
from os import getenv as env, getcwd
from os.path import dirname, abspath, join
from privex.helpers import env_bool, env_int, env_csv, env_cast
import dotenv

BASE_DIR = dirname(dirname(abspath(__file__)))

dotenv.load_dotenv()
dotenv.load_dotenv(join(BASE_DIR, '.env'))
dotenv.load_dotenv(join(getcwd(), '.env'))

DEBUG = env_bool('DEBUG', False)

verbose: bool = env_bool('VERBOSE', DEBUG)
quiet: bool = env_bool('QUIET', False)

LOG_DIR = join(BASE_DIR, 'logs')

# Valid environment log levels (from least to most severe) are:
# DEBUG, INFO, WARNING, ERROR, FATAL, CRITICAL
LOG_LEVEL = env('LOG_LEVEL', None)
LOG_LEVEL = logging.getLevelName(str(LOG_LEVEL).upper()) if LOG_LEVEL is not None else None

if LOG_LEVEL is None:
    LOG_LEVEL = logging.DEBUG if DEBUG or verbose else logging.INFO
    LOG_LEVEL = logging.CRITICAL if quiet else LOG_LEVEL

RPC_TIMEOUT = env_int('RPC_TIMEOUT', 3)
MAX_TRIES = env_int('MAX_TRIES', 3)
RETRY_DELAY = env_cast('RETRY_DELAY', cast=float, env_default=2.0)
PUB_PREFIX = env('PUB_PREFIX', 'STM')  # Used as part of the thorough plugin tests for checking correct keys are returned


TEST_PLUGINS_LIST = env_csv('TEST_PLUGIN_LIST', [])
"""
Controls which plugins are tested by :class:`.RPCScanner` when :attr:`rpcscanner.settings.plugins` is
set to ``True``.

If the TEST_PLUGINS_LIST is empty, it will be populated automatically when the module container :class:`.MethodTests`
is loaded, which will replace it with a tuple containing :attr:`rpcscanner.MethodTests.METHOD_MAP`.
"""

EXTRA_PLUGINS_LIST = env_csv('EXTRA_PLUGINS_LIST', [])
"""
Additional RPC methods to test - add to your ``.env`` as comma separated RPC method names.

Will be appended to ``TEST_PLUGIN_LIST``

Example ``.env`` entry::
    
    EXTRA_PLUGINS_LIST=condenser_api.some_method,block_api.another_method


"""
TEST_PLUGINS_LIST = tuple(TEST_PLUGINS_LIST + EXTRA_PLUGINS_LIST)

GOOD_RETURN_CODE = env_int('GOOD_RETURN_CODE', 0)
BAD_RETURN_CODE = env_int('BAD_RETURN_CODE', 8)


plugins: bool = env_bool('PLUGINS', False)
node_file: str = env('NODE_FILE', 'nodes.conf')
test_account: str = env('TEST_ACCOUNT', 'someguy123')
test_post: str = env('TEST_POST', 'announcement-soft-fork-0-22-2-released-steem-in-a-box-update')
