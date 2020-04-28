import twisted.internet.reactor
from twisted.internet.defer import inlineCallbacks

from rpcscanner.core import PUB_PREFIX
from rpcscanner.rpc import rpc
from rpcscanner.exceptions import ValidationError
from rpcscanner import settings
from typing import List, Dict, Tuple
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
        self.test_post = settings.test_post.strip()
        self.METHOD_MAP = {
            'account_history_api.get_account_history': self.test_account_history,
            'condenser_api.get_account_history': self.test_condenser_history,
            'condenser_api.get_accounts': self.test_condenser_account,
            'condenser_api.get_blog': self.test_get_blog,
            'condenser_api.get_content': self.test_get_content,
            'condenser_api.get_followers': self.test_get_followers,
            'condenser_api.get_witness_by_account': self.test_condenser_witness,
            'bridge.get_trending_topics': self.test_bridge_trending_topics
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
    
    @inlineCallbacks
    def test_bridge_trending_topics(self):
        """Test a node for functioning bridge.get_trending_topics"""
        mtd = 'bridge.get_trending_topics'
        count = 10
        params = {"limit": count}
        res, tt, tr = yield rpc(self.reactor, self.host, mtd, params)

        log.debug(f'bridge.get_trending_topics check if result from {self.host} has valid trending topics')
        
        for a in res:
            if len(a) != 2:
                raise ValidationError(f"Community result contained {len(a)} items (expected 2) in bridge.get_trending_topics response from {self.host}")
            
            if 'hive-' not in a[0]:
                raise ValidationError(f"Invalid community '{a[0]}' in bridge.get_trending_topics response from {self.host}")

        return res, tt, tr
    @inlineCallbacks
    def test_get_blog(self):
        """Test a node for functioning full node get_blog"""
        mtd = 'condenser_api.get_blog'
        params = [self.test_acc, -1, 10]
        res, tt, tr = yield rpc(self.reactor, self.host, mtd, params)

        log.debug(f'get_blog check if result from {self.host} has blog, entry_id, comment, and comment.body')
        
        self._check_blog(res)
        return res, tt, tr

    @inlineCallbacks
    def test_get_content(self):
        """Test a node for functioning full node get_content"""
        mtd = 'condenser_api.get_content'
        params = [self.test_acc, self.test_post]
        res, tt, tr = yield rpc(self.reactor, self.host, mtd, params)

        log.debug(f'get_content check if result from {self.host} has title, author and body')
        
        self._check_blog_item(res)
        return res, tt, tr
    
    @inlineCallbacks
    def test_get_followers(self):
        """Test a node for functioning full node get_followers"""
        mtd = 'condenser_api.get_followers'
        count = 10
        params = [self.test_acc, None, "blog", count]
        res, tt, tr = yield rpc(self.reactor, self.host, mtd, params)

        
        log.debug(f'Length check if result from {self.host} has at least {count} results')
        follow_len = len(res)
        if follow_len < count:
            raise ValidationError(f"Too little followers. Only {follow_len} follower results (<{count}) for {self.host}")

        log.debug(f'get_followers check if result from {self.host} has valid follower items')

        for follower in res:
            self._check_follower(follower)
        
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

    def _check_follower(self, item: dict):
        if 'follower' not in item:
            raise ValidationError(f"JSON key 'follower' not found in follower item from RPC query for node {self.host}")
        if 'following' not in item:
            raise ValidationError(f"JSON key 'following' not found in follower item from RPC query for node {self.host}")
        if 'what' not in item:
            raise ValidationError(f"JSON key 'what' not found in follower item from RPC query for node {self.host}")
    
    def _check_blog_item(self, item: dict):
        if 'body' not in item:
            raise ValidationError(f"JSON key 'body' not found in blog content from RPC query for node {self.host}")
        
        if 'author' not in item:
            raise ValidationError(f"JSON key 'author' not found in blog content from RPC query for node {self.host}")

        if 'category' not in item:
            raise ValidationError(f"JSON key 'category' not found in blog content from RPC query for node {self.host}")

        if 'title' not in item:
            raise ValidationError(f"JSON key 'title' not found in blog content from RPC query for node {self.host}")
    
    def _check_blog(self, response: List[dict], count=10):
        """Small helper function to verify an RPC response contains valid blog records"""
        res = response
        
        log.debug(f'Length check if result from {self.host} has at least {count} results')
        blog_len = len(res)
        if blog_len < count:
            raise ValidationError(f"Too little blog posts. Only {blog_len} blog results (<{count}) for {self.host}")

        # Scan all items in the blog
        for item in res:
            if 'blog' not in item:
                raise ValidationError(f"JSON key 'blog' not found in RPC query for node {self.host}")
            if 'entry_id' not in item:
                raise ValidationError(f"JSON key 'entry_id' not found in RPC query for node {self.host}")
            if 'comment' not in item:
                raise ValidationError(f"JSON key 'comment' not found in RPC query for node {self.host}")

            if 'body' not in item['comment']:
                raise ValidationError(f"JSON key 'body' not found in 'comment' dict from RPC query for node {self.host}")


    
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