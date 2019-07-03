# from dataclasses import dataclass

from os.path import dirname, abspath, join
import logging
from typing import List

from rpcscanner import settings

log = logging.getLogger(__name__)
BASE_DIR = dirname(dirname(abspath(__file__)))


RPC_TIMEOUT = 5
MAX_TRIES = 3
PUB_PREFIX = 'STM'   # Used as part of the thorough plugin tests for checking correct keys are returned


TEST_PLUGINS_LIST = (
    'condenser_api.get_account_history',
    'account_history_api.get_account_history',
    'condenser_api.get_witness_by_account',
    'condenser_api.get_accounts'
)


def load_nodes(file: str) -> List[str]:
    # nodes to be specified line by line. format: http://gtg.steem.house:8090
    node_list = open(join(BASE_DIR, file), 'r').readlines()
    node_list = [n.strip() for n in node_list]
    # Allow nodes to be commented out with # symbol
    return [n for n in node_list if n[0] != '#']


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

