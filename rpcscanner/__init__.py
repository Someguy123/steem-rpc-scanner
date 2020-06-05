"""

Using RPCScanner API within apps
--------------------------------

**High level usage with :class:`.RPCScanner`**

Basic usage of :class:`.RPCScanner` with :meth:`rpcscanner.RPCScanner.RPCScanner.scan_nodes` ::

    >>> from rpcscanner import RPCScanner, settings, MethodTests
    >>> # By default, testing each individual plugin when running scan_nodes is disabled.
    >>> # You can enable plugin testing by changing settings.plugins to True
    >>> settings.plugins = True
    >>> # Instantiate RPCScanner with a list of RPC nodes - http or https, non-standard ports are supported
    >>> # via colon format, e.g. http://my.example.rpc:8091
    >>> scanner = RPCScanner(['https://hived.privex.io', 'https://hived.hive-engine.com'])
    >>> # scan_nodes is the key method of the class, which handles calling the 4 to 5 methods that handle the
    >>> # various stages of scanning the passed nodes
    >>> await scanner.scan_nodes(quiet=True)
    >>> # Use .get_node to get a NodeStatus dataclass object, which allows easy querying of various information about a scanned node.
    >>> nd = scanner.get_node('https://hived.privex.io')
    >>> nd.version
    '0.23.0'
    >>> nd.plugins
    ['bridge.get_trending_topics', 'condenser_api.get_account_history',
     'condenser_api.get_content', 'condenser_api.get_followers',
     'condenser_api.get_witness_by_account', 'condenser_api.get_accounts',
     'account_history_api.get_account_history', 'condenser_api.get_blog']
    >>> nd.timing
    {'ident': 0.3845839500427246,
     'config': 0.4896061420440674,
     'props': 0.49631738662719727}

**Mid-level usage with direct plugin testing via :class:`.MethodTests`**

Testing individual supported RPC methods with :meth:`.MethodTests.test`::
  
    >>> mt = MethodTests('https://hived.privex.io')
    >>> res, time_taken_sec, tries = await mt.test('account_history_api.get_account_history')
    >>> res['history'][0]
    [1540217, {
        'trx_id': '0000000000000000000000000000000000000000', 'block': 43795325, 'trx_in_block': 4294967295,
        'op_in_trx': 0, 'virtual_op': 1, 'timestamp': '2020-05-28T11:43:48',
        'op': {
            'type': 'producer_reward_operation',
            'value': {'producer': 'someguy123', 'vesting_shares': {'amount': '469463734', 'precision': 6, 'nai': '@@000000037'}}
        }
    }]
    >>> time_taken_sec
    0.3937380313873291
    >>> tries
    1

Testing all supported RPC methods with :meth:`.MethodTests.test_all`::

    >>> plugtests = await mt.test_all()
    >>> plugtests.methods
    {'account_history_api.get_account_history': True, 'condenser_api.get_account_history': True,
     'condenser_api.get_accounts': True, 'condenser_api.get_blog': True, 'condenser_api.get_content': True,
     'condenser_api.get_followers': True, 'condenser_api.get_witness_by_account': True, 'bridge.get_trending_topics': True}
    >>> plugtests.errors
    {}
    >>> plugtests.results['condenser_api.get_witness_by_account']
    (
        {'id': 11578, 'owner': 'someguy123', 'created': '2016-08-09T00:03:18', 'url': 'https://peakd.com/@someguy123/', ...},
        0.7117502689361572,
        1
    )

**Lower level usage**

Low level testing using :func:`rpcscanner.rpc.rpc` function call::
    
    >>> from rpcscanner.rpc import rpc
    >>> rd, timing, tries = await rpc('https://hived.privex.io', 'condenser_api.get_dynamic_global_properties', [])
    >>> rd
    {'head_block_number': 43797319,
     'head_block_id': '029c4b47edeaec18774032a3a5aee5b8dddc0319',
     'time': '2020-05-28T13:23:42',
     'current_witness': 'someguy123',
     'total_pow': 514415,
     'num_pow_witnesses': 172,
     'virtual_supply': '376318066.671 HIVE',
     ...
    }
    >>> timing
    0.4440031051635742
    >>> tries
    1


"""
from rpcscanner.core import *
from rpcscanner.rpc import NodePlug, identify_node
from rpcscanner.MethodTests import MethodTests, METHOD_MAP, get_supported_methods, get_filtered_methods
from rpcscanner.exceptions import *
from rpcscanner.RPCScanner import RPCScanner, NodeStatus, NETWORK_COINS, TOTAL_STAGES_TRACKED

