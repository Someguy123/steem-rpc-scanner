"""
The settings in this file will normally be overwritten by the CLI tool, from either
a .env file, or arguments passed on the CLI.
"""
import logging
import sys
from os import getenv as env, getcwd
from os.path import dirname, abspath, join, isabs, exists, expanduser, basename
from typing import Optional, List

from privex.helpers import env_bool, env_int, env_csv, env_cast, empty_if, empty
import dotenv

BASE_DIR = dirname(dirname(abspath(__file__)))

dotenv.load_dotenv()
dotenv.load_dotenv(join(BASE_DIR, '.env'))
dotenv.load_dotenv(join(getcwd(), '.env'))

SEARCH_PATHS = env_csv('SEARCH_PATHS', [getcwd(), BASE_DIR, '~', '/'])


def scan_paths(filename: str, search_dirs: List[str] = None) -> Optional[str]:
    search_dirs = empty_if(search_dirs, SEARCH_PATHS)
    for b in search_dirs:
        f = abspath(expanduser(join(b, filename)))
        if exists(f): return f
    return None


def find_parent(filename: str, rise=1, throw=True) -> Optional[str]:
    parent = dirname(filename)
    
    if isabs(parent):
        if exists(parent):
            return parent
        if rise > 1: return find_parent(dirname(parent), rise=rise-1, throw=throw)
        if throw: raise FileNotFoundError(f"File/folder '{filename}' parent '{parent}' was not found (abs path parent)")
        return None
    
    parent = scan_paths(parent)
    if not empty(parent):
        return parent
    
    if rise > 1: return find_parent(dirname(parent), rise=rise - 1, throw=throw)
    if throw: raise FileNotFoundError(f"File/folder '{filename}' parent '{parent}' was not found (rel path parent search)")
    return None
    

def find_file(filename: str, throw=True) -> Optional[str]:
    """
    Locate the file ``filename``. If ``filename`` is absolute, simply checks if the path exists and returns it intact - otherwise
    raises :class:`.FileNotFoundError`.

    If ``filename`` is relative, searches for the file within the following paths in order:

        * Current working directory
        * :attr:`.BASE_DIR` (root folder of project)
        * ``~/`` (current user's home folder)
        * ``/`` (root folder of system)

    :param str filename: A relative or absolute path to a file to locate.
    :param bool throw: (default: ``True``) If ``True``, will raise :class:`.FileNotFoundError` if ``filename`` cannot be located.
                       If set to ``False``, will simply return ``None`` instead of raising an exception.

    :raises FileNotFoundError: Raised when ``throw`` is ``True`` and ``filename`` cannot be located.

    :return Optional[str] full_path: The full, absolute path to the file if it was found. If ``throw`` is ``False`` - ``None`` may be
                                     returned if ``filename`` isn't found.
    """
    if isabs(filename):
        if not exists(filename):
            if throw: raise FileNotFoundError(f"File/folder '{filename}' was not found (abs path)")
            return None
        return filename
    
    for b in SEARCH_PATHS:
        f = abspath(expanduser(join(b, filename)))
        if exists(f): return f
    
    if throw: raise FileNotFoundError(f"File/folder '{filename}' was not found (rel path search)")
    return None


DEBUG = env_bool('DEBUG', False)

verbose: bool = env_bool('VERBOSE', DEBUG)
quiet: bool = env_bool('QUIET', False)

_LOG_DIR = env('LOG_DIR', join(BASE_DIR, 'logs'))
try:
    LOG_DIR = abspath(join(find_parent(_LOG_DIR), basename(_LOG_DIR)))
except FileNotFoundError as e:
    print(
        f" [!!!] WARNING: Failed to validate LOG_DIR '{_LOG_DIR}' - could not verify parent folder exists."
        f"Exception was: {type(e)} {str(e)}", file=sys.stderr
    )
    print(f" [!!!] Setting LOG_DIR to original value - may be fixed when log folder + containing folders are auto-created.",
          file=sys.stderr)
    LOG_DIR = _LOG_DIR

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

SKIP_API_LIST = env_csv('SKIP_API_LIST', env_csv('SKIP_APIS', []))

GOOD_RETURN_CODE = env_int('GOOD_RETURN_CODE', 0)
BAD_RETURN_CODE = env_int('BAD_RETURN_CODE', 8)


plugins: bool = env_bool('PLUGINS', False)
node_file: str = env('NODE_FILE', 'nodes.conf')
test_account: str = env('TEST_ACCOUNT', 'someguy123')
test_post: str = env('TEST_POST', 'announcement-soft-fork-0-22-2-released-steem-in-a-box-update')
MAX_SCORE = env_int('MAX_SCORE', 50)


