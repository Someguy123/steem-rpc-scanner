import asyncio

# import twisted.internet.reactor
from privex.helpers import DictObject, empty_if
# from twisted.internet.defer import inlineCallbacks

from rpcscanner.settings import PUB_PREFIX
from rpcscanner.rpc import rpc
from rpcscanner.exceptions import ValidationError
from rpcscanner import settings
from typing import List, Dict, Tuple, Union, Awaitable, Coroutine
import logging

log = logging.getLogger(__name__)


class MethodTests:
    """
    Thorough plugin test functions for RPC nodes, to verify functionality.

    Basic usage:

    >>> mt = MethodTests('https://steemd.privex.io')
    >>> try:
    ...     res, time_taken, total_retries = await mt.test('account_history_api.get_account_history')
    >>> except Exception:
    ...     log.exception('Account history test failed for steemd.privex.io')

    """

    def __init__(self, host: str):
        self.host = host
        self.test_acc = settings.test_account.lower().strip()
        self.test_post = settings.test_post.strip()
        self.loop = asyncio.get_event_loop()

    async def test(self, api_name: str) -> Tuple[Union[list, dict], float, int]:
        """Call a test method by the API method name"""
        log.debug(f'MethodTests.test now calling API {api_name}')
        res = await METHOD_MAP[api_name](self, self.host)
        # log.debug(f'MethodTest.test got result for {api_name}: {res}')
        return res
    
    async def test_all(self, whitelist: List[str] = None, blacklist: List[str] = None) -> Union[DictObject, Dict[str, dict]]:
        """
        Tests all supported RPC methods by :class:`.MethodTests` against :attr:`.host`, optionally specifying either a
        ``whitelist`` or ``blacklist``
        
        This method returns a :class:`.DictObject` containing three keys::
        
         - ``methods`` - A :class:`.dict` of JSONRPC string methods mapped to booleans, with ``True`` meaning the
            method was tested without any problems, while ``False`` means that an error occurred while testing this method.
        
         - ``errors`` - A :class:`.dict` which contains JSONRPC string methods mapped to the :class:`.Exception` which they raised.
                        Only methods which raised an exception (i.e. those marked ``False`` in the ``methods`` dict) will be present here.
        
         - ``results`` - A :class:`.dict` which contains JSONRPC string methods mapped to the result their class testing method returned.
                        This is usually a ``Tuple[Union[list,dict], float, int]``, which contains ``(response, time_taken_sec, tries)``
        
        :param List[str] whitelist: A list of JSONRPC methods to exclusively test, e.g.
                                    ``['account_history_api.get_account_history', 'condenser_api.get_accounts']``
        :param List[str] blacklist: A list of JSONRPC methods to skip testing, e.g.  ``['bridge.get_trending_topics']``
        :return Union[DictObject,Dict[str, dict]] res: A :class:`.DictObject` containing three :class:`.dict`'s: ``methods``, ``errors``,
                                                        and ``results``. Full explanation of returned object in main pydoc body for this
                                                        method :meth:`.test_all`
        """
        res = DictObject(methods={}, errors={}, results={})
        tasks = []
        for meth, func in METHOD_MAP.items():
            if whitelist is not None and meth not in whitelist:
                log.debug("Skipping RPC method %s against host %s as method is not present in whitelist.", meth, self.host)
                continue
            if blacklist is not None and meth in blacklist:
                log.debug("Skipping RPC method %s against host %s as method is present in blacklist.", meth, self.host)
                continue
            tasks.append(self.loop.create_task(self._test_meth(func, meth)))
        for t in tasks:
            status, result, error, meth = await t
            res.methods[meth] = status
            if result is not None: res.results[meth] = result
            if error is not None: res.errors[meth] = error
        return res

    async def _test_meth(self, func: Union[Coroutine, Awaitable, callable], meth: str):
        
        status, result, error = False, None, None
        try:
            log.debug("Testing RPC method %s against host %s", meth, self.host)
            result = await func(self, self.host)
            status = True
            log.debug("Successfully ran RPC method %s against host %s", meth, self.host)
        except Exception as e:
            log.exception("Error while testing method %s on host %s", meth, self.host)
            status = False
            error = e
        
        return status, result, error, meth

    # @retry_on_err(max_retries=MAX_TRIES)
    async def test_account_history(self, host=None, *args, **kwargs) -> Tuple[Union[list, dict], float, int]:
        """Test a node for functioning account_history_api account history"""
        host = empty_if(host, self.host)
        mtd = 'account_history_api.get_account_history'
        params = dict(account=self.test_acc, start=-1, limit=100)
        res, tt, tr = await rpc(host=host, method=mtd, params=params)

        log.debug(f'History check if result from {host} has history key')
        if 'history' not in res:
            raise ValidationError(f"JSON key 'history' not found in RPC query for node {host}")

        self._check_hist(res['history'])
        return res, tt, tr
    
    async def test_bridge_trending_topics(self, host=None, *args, **kwargs) -> Tuple[Union[list, dict], float, int]:
        """Test a node for functioning bridge.get_trending_topics"""
        host = empty_if(host, self.host)
        mtd = 'bridge.get_trending_topics'
        count = 10
        params = {"limit": count}
        res, tt, tr = await rpc(host=host, method=mtd, params=params)

        log.debug(f'bridge.get_trending_topics check if result from {host} has valid trending topics')
        
        for a in res:
            if len(a) != 2:
                raise ValidationError(f"Community result contained {len(a)} items (expected 2) in bridge.get_trending_topics response from {host}")
            
            if 'hive-' not in a[0]:
                raise ValidationError(f"Invalid community '{a[0]}' in bridge.get_trending_topics response from {host}")

        return res, tt, tr
    
    async def test_get_blog(self, host=None, *args, **kwargs) -> Tuple[Union[list, dict], float, int]:
        """Test a node for functioning full node get_blog"""
        host = empty_if(host, self.host)
        mtd = 'condenser_api.get_blog'
        params = [self.test_acc, -1, 10]
        res, tt, tr = await rpc(host=host, method=mtd, params=params)

        log.debug(f'get_blog check if result from {host} has blog, entry_id, comment, and comment.body')
        
        self._check_blog(res)
        return res, tt, tr

    async def test_get_content(self, host=None, *args, **kwargs) -> Tuple[Union[list, dict], float, int]:
        """Test a node for functioning full node get_content"""
        host = empty_if(host, self.host)
        mtd = 'condenser_api.get_content'
        params = [self.test_acc, self.test_post]
        res, tt, tr = await rpc(host=host, method=mtd, params=params)

        log.debug(f'get_content check if result from {host} has title, author and body')
        
        self._check_blog_item(res)
        return res, tt, tr
    
    async def test_get_followers(self, host=None, *args, **kwargs) -> Tuple[Union[list, dict], float, int]:
        """Test a node for functioning full node get_followers"""
        host = empty_if(host, self.host)
        mtd = 'condenser_api.get_followers'
        count = 10
        params = [self.test_acc, None, "blog", count]
        res, tt, tr = await rpc(host=host, method=mtd, params=params)

        log.debug(f'Length check if result from {host} has at least {count} results')
        follow_len = len(res)
        if follow_len < count:
            raise ValidationError(f"Too little followers. Only {follow_len} follower results (<{count}) for {host}")

        log.debug(f'get_followers check if result from {host} has valid follower items')

        for follower in res:
            self._check_follower(follower)
        
        return res, tt, tr
    
    # @retry_on_err(max_retries=MAX_TRIES)
    async def test_condenser_history(self, host=None, *args, **kwargs) -> Tuple[Union[list, dict], float, int]:
        """Test a node for functioning condenser_api account history"""
        host = empty_if(host, self.host)
        mtd = 'condenser_api.get_account_history'
        params = [self.test_acc, -100, 100]
        res, tt, tr = await rpc(host=host, method=mtd, params=params)

        self._check_hist(res)
        return res, tt, tr

    # @retry_on_err(max_retries=MAX_TRIES)
    async def test_condenser_account(self, host=None, *args, **kwargs) -> Tuple[Union[list, dict], float, int]:
        """Test a node for functioning condenser_api get_accounts query"""
        host = empty_if(host, self.host)
        mtd, params = 'condenser_api.get_accounts', [ [self.test_acc], ]
        res, tt, tr = await rpc(host=host, method=mtd, params=params)

        # Normal python exceptions such as IndexError should be thrown if the data isn't formatted correctly
        acc = res[0]
        log.debug(f'Checking if result from {host} has user {self.test_acc}')
        if acc['name'].lower().strip() != self.test_acc:
            raise ValidationError(f"Account {acc['name']} was returned, but expected {self.test_acc} for node {host}")
        log.debug(f'Success - result from {host} has user {self.test_acc}')
        return res, tt, tr

    # @retry_on_err(max_retries=MAX_TRIES)
    async def test_condenser_witness(self, host=None, *args, **kwargs) -> Tuple[Union[list, dict], float, int]:
        """Test a node for functioning witness lookup (get_witness_by_account)"""
        host = empty_if(host, self.host)
        mtd, params = 'condenser_api.get_witness_by_account', [self.test_acc]
        res, tt, tr = await rpc(host=host, method=mtd, params=params)
        if res['owner'].lower().strip() != self.test_acc:
            raise ValidationError(f"Witness {res['owner']} was returned, but expected {self.test_acc} for node {host}")
        prf = res['signing_key'][0:3]
        if prf != PUB_PREFIX:
            raise ValidationError(f"Signing key prefix was {prf} but expected {PUB_PREFIX} for node {host}")

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


METHOD_MAP = {
    'account_history_api.get_account_history': MethodTests.test_account_history,
    'condenser_api.get_account_history':       MethodTests.test_condenser_history,
    'condenser_api.get_accounts':              MethodTests.test_condenser_account,
    'condenser_api.get_blog':                  MethodTests.test_get_blog,
    'condenser_api.get_content':               MethodTests.test_get_content,
    'condenser_api.get_followers':             MethodTests.test_get_followers,
    'condenser_api.get_witness_by_account':    MethodTests.test_condenser_witness,
    'bridge.get_trending_topics':              MethodTests.test_bridge_trending_topics
}


if len(settings.TEST_PLUGINS_LIST) == 0:
    settings.TEST_PLUGINS_LIST = tuple(METHOD_MAP.keys())
