# from dataclasses import dataclass

from os.path import dirname, abspath
import logging

log = logging.getLogger(__name__)
BASE_DIR = dirname(dirname(abspath(__file__)))


RPC_TIMEOUT = 5
MAX_TRIES = 5
PUB_PREFIX = 'STM'   # Used as part of the thorough plugin tests for checking correct keys are returned


TEST_PLUGINS_LIST = (
    'condenser_api.get_account_history',
    'account_history_api.get_account_history',
    'condenser_api.get_witness_by_account',
    'condenser_api.get_accounts'
)


# @dataclass
# class ScannerSettings:
#     verbose: bool = False
#     quiet: bool = False
#     plugins: bool = False
#     node_file: str = 'nodes.txt'
#     test_account: str = 'someguy123'
#
#
# settings = ScannerSettings()

