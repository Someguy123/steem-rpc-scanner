import twisted.internet.reactor
from twisted.internet.defer import inlineCallbacks

from rpcscanner.core import PUB_PREFIX
from rpcscanner.rpc import rpc
from rpcscanner.exceptions import ValidationError
from rpcscanner import settings
import logging

log = logging.getLogger(__name__)


class MethodTests:
    """
    Thorough plugin test functions for RPC nodes, to verify functionality.

    Basic usage:

    >>> mt = MethodTests('https://steemd.privex.io', reactor)
    >>> try:
    ...     res, time_taken, total_retries = yield mt.test('account_history_api.get_account_history')
    >>> except Exception:
    ...     log.exception('Account history test failed for steemd.privex.io')

    """

    def __init__(self, host: str, reactor: twisted.internet.reactor):
        self.host, self.reactor = host, reactor
        self.test_acc = settings.test_account.lower().strip()
        self.METHOD_MAP = {
            'account_history_api.get_account_history': self.test_account_history,
            'condenser_api.get_account_history': self.test_condenser_history,
            'condenser_api.get_accounts': self.test_condenser_account,
            'condenser_api.get_witness_by_account': self.test_condenser_witness,
        }

    @inlineCallbacks
    def test(self, api_name):
        """Call a test method by the API method name"""
        log.debug(f'MethodTests.test now calling API {api_name}')
        res = yield self.METHOD_MAP[api_name]()
        # log.debug(f'MethodTest.test got result for {api_name}: {res}')
        return res

    # @retry_on_err(max_retries=MAX_TRIES)
    @inlineCallbacks
    def test_account_history(self):
        """Test a node for functioning account_history_api account history"""
        mtd = 'account_history_api.get_account_history'
        params = dict(account=self.test_acc, start=-1, limit=100)
        res, tt, tr = yield rpc(self.reactor, self.host, mtd, params)

        log.debug(f'History check if result from {self.host} has history key')
        if 'history' not in res:
            raise ValidationError(f"JSON key 'history' not found in RPC query for node {self.host}")

        self._check_hist(res['history'])
        return res, tt, tr

    # @retry_on_err(max_retries=MAX_TRIES)
    @inlineCallbacks
    def test_condenser_history(self):
        """Test a node for functioning condenser_api account history"""
        mtd = 'condenser_api.get_account_history'
        params = [self.test_acc, -100, 100]
        res, tt, tr = yield rpc(self.reactor, self.host, mtd, params)

        self._check_hist(res)
        return res, tt, tr

    # @retry_on_err(max_retries=MAX_TRIES)
    @inlineCallbacks
    def test_condenser_account(self):
        """Test a node for functioning condenser_api get_accounts query"""
        mtd, params = 'condenser_api.get_accounts', [ [self.test_acc], ]
        res, tt, tr = yield rpc(self.reactor, self.host, mtd, params)

        # Normal python exceptions such as IndexError should be thrown if the data isn't formatted correctly
        acc = res[0]
        log.debug(f'Checking if result from {self.host} has user {self.test_acc}')
        if acc['name'].lower().strip() != self.test_acc:
            raise ValidationError(f"Account {acc['name']} was returned, but expected {self.test_acc} for node {self.host}")
        log.debug(f'Success - result from {self.host} has user {self.test_acc}')
        return res, tt, tr

    # @retry_on_err(max_retries=MAX_TRIES)
    @inlineCallbacks
    def test_condenser_witness(self):
        """Test a node for functioning witness lookup (get_witness_by_account)"""
        mtd, params = 'condenser_api.get_witness_by_account', [self.test_acc]
        res, tt, tr = yield rpc(self.reactor, self.host, mtd, params)
        if res['owner'].lower().strip() != self.test_acc:
            raise ValidationError(f"Witness {res['owner']} was returned, but expected {self.test_acc} for node {self.host}")
        prf = res['signing_key'][0:3]
        if prf != PUB_PREFIX:
            raise ValidationError(f"Signing key prefix was {prf} but expected {PUB_PREFIX} for node {self.host}")

        return res, tt, tr

    def _check_hist(self, response: dict):
        """Small helper function to verify an RPC response contains valid account history records"""
        res = response

        # Get the first item from the history
        hist = res[0]
        if type(hist[0]) != int or type(hist[1]) != dict:
            raise ValidationError(f"History data is malformed in RPC query for node {self.host}")

        log.debug(f'Length check if result from {self.host} has at least 5 results')
        hist_len = len(res)
        if hist_len < 5:
            raise ValidationError(f"Too little history. Only {hist_len} history results (<5) for {self.host}")