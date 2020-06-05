import logging
from argparse import ArgumentParser, Namespace
from typing import Union, List, Set
from privex.helpers import DictObject, empty, empty_if, parse_csv, is_true
from rpcscanner.MethodTests import get_filtered_methods
from rpcscanner import settings
from rpcscanner.core import clear_handlers, set_logging_level

log = logging.getLogger(__name__)


help_texts = DictObject(
    skip_apis=f"A comma separated list of API methods to exclude from plugin testing. Current enabled API tests: ",
    plugins='Run thorough plugin testing after basic filter tests complete.',
    no_plugins=f'Do NOT test individual plugin APIs when scanning RPC nodes. This will speed up scanning, but '
               f'will give less accurate test results as only very basic API tests will be done. NOTE: When plugin '
               f'scanning is disabled, scores still go up to {settings.MAX_SCORE}, but node scores will not be degraded '
               f'by plugin test results.',
    nodefile=f'Specify a custom file to read nodes from (default: {settings.node_file}). You may pass "-" to read the list of nodes'
             f'from STDIN instead of a file.',
    node='Individual RPC Node with http(s):// prefix. Optionally you can specify a port at the end using a colon. E.g. '
         'https://hived.privex.io:8293',
    params=f"If you want to test an unsupported RPC method - you can pass parameters to send when calling the unsupported method. This "
           f"should be specified as a JSON encoded string. If not specified, defaults to '[]'. [ONLY USED FOR UNSUPPORTED METHODS]",
    verbose='Verbose logging mode', quiet='Quiet logging mode'
)


def get_arg_defaults() -> DictObject:
    """
    Generates a :class:`.DictObject` containing sane argument defaults for use with a :class:`.ArgumentParser` instance.
    """
    return DictObject(
        skip_apis='', plugins=settings.plugins, nodefile=settings.node_file, verbose=settings.verbose,
        quiet=settings.quiet, params='[]'
    )


def handle_args(args: Namespace):
    """
    
    
    
        >>> parser = ArgumentParser(description="my arg parser")
        >>> add_arguments(parser, 'verbose', 'quiet', 'nodefile')
        >>> args = parser.parse_args()
        >>> handle_args(args)

    :param args:
    :return:
    """
    if 'skip_apis' in args and not empty(args.skip_apis, itr=True):
        settings.SKIP_API_LIST = parse_csv(args.skip_apis)
    
    if args.quiet:
        settings.quiet = True
        settings.verbose = False
        clear_handlers('rpcscanner', None)
        set_logging_level(logging.CRITICAL, None)
    elif args.verbose:
        settings.quiet = False
        settings.verbose = True
        clear_handlers('rpcscanner', None)
        set_logging_level(logging.DEBUG, None)
    
    if 'nodefile' in args: settings.node_file = args.nodefile
    if 'node_file' in args: settings.node_file = args.node_file
    if 'plugins' in args: settings.plugins = is_true(args.plugins)


def add_defaults(parser: ArgumentParser, remove_defaults: Union[List[str], Set[str], tuple] = None, **overrides):
    """
    Add the defaults from :func:`.get_arg_defaults` to the argument parser ``parser``.
    
    New defaults can be added, and existing defaults from :func:`.get_arg_defaults` can be overrided by specifying
    new/override defaults as kwargs.
    
    If you need to prevent certain defaults from :func:`.get_arg_defaults` or the passed ``overrides` kwargs from
    being set on ``parser``,  pass their keys as a :class:`list` / :class:`set` / :class:`tuple` via the
    ``remove_defaults`` argument.
    
    Below is an example - create an arg parser, add ``--plugins`` to ``parser``, then add the common defaults to it. Remove the
    default for ``nodefile``, and override the default ``skip_apis`` to contain ``'bridge.get_trending_topics'``.
    
    Example::
    
        >>> parser = ArgumentParser(description="my arg parser")
        >>> add_plugins(parser)
        >>> add_defaults(parser, remove_defaults=['nodefile'], skip_apis='bridge.get_trending_topics')
    
    :param ArgumentParser parser: A :class:`.ArgumentParser` instance
    :param List[str]|Set[str]|tuple remove_defaults: An optional list, set or tuple containing keys to remove from the defaults
                                                     before adding them to ``parser``
    :param overrides: Keyword arguments containing any additional defaults to add, or pre-existing defaults from :func:`.get_arg_default`
                      to override (replace).
    :return DictObject defs: A :class:`.DictObject` containing the defaults which were set on ``parser``
    """
    defs = DictObject({**get_arg_defaults(), **overrides})
    if not empty(remove_defaults, itr=True):
        for k in defs.keys():
            if k not in remove_defaults:
                continue
            del defs[k]
    parser.set_defaults(**defs)
    return defs


def add_defaults_limit(parser: ArgumentParser, *arg_names, **overrides):
    gen_defs = get_arg_defaults()
    defs = DictObject({**{a: gen_defs[a] for a in arg_names if a in gen_defs}, **overrides})
    # defs = DictObject({**defs, **overrides})
    parser.set_defaults(**defs)
    return defs
    

def add_skip_apis(parser: ArgumentParser, help_text=help_texts.skip_apis, append_apis=True):
    if append_apis:
        help_text += ', '.join(get_filtered_methods())
    parser.add_argument('-m', '--skip-api', dest='skip_apis', default='', help=help_text)


def add_plugins(parser: ArgumentParser, help_text=help_texts.plugins):
    parser.add_argument('--plugins', action='store_true', dest='plugins', default=settings.plugins, help=help_text)


def add_no_plugins(parser: ArgumentParser, help_text=help_texts.no_plugins):
    parser.add_argument('-n', '--no-plugins', dest='plugins', action='store_false', default=settings.plugins, help=help_text)


def add_nodefile(parser: ArgumentParser, help_text=help_texts.nodefile):
    parser.add_argument('-f', '--node-file', dest='nodefile', default=settings.node_file, help=help_text)


def add_rpc_node(parser: ArgumentParser, help_text=help_texts.node):
    parser.add_argument('node', help=help_text)


def add_verbose(parser: ArgumentParser, help_text=help_texts.verbose):
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=settings.verbose, help=help_text)


def add_quiet(parser: ArgumentParser, help_text=help_texts.quiet):
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true', default=settings.quiet, help=help_text)


def add_rpc_params(parser: ArgumentParser, help_text=help_texts.params):
    parser.add_argument('--params', default='[]', help=help_text)


ARG_MAP = DictObject(
    skip_apis=add_skip_apis,
    plugins=add_plugins,
    no_plugins=add_no_plugins,
    nodefile=add_nodefile,
    node=add_rpc_node,
    params=add_rpc_params,
    verbose=add_verbose, quiet=add_quiet
)


def add_arguments(parser: ArgumentParser, *arg_names, set_defaults=False, overrides: dict = None, **arg_help):
    """

    Examples::
    
        >>> parser = ArgumentParser(description="my arg parser")
        >>> # Basic usage
        >>> add_arguments(parser, 'verbose', 'quiet', 'nodefile', 'no_plugins', set_defaults=True)
        >>> # More advanced usage using 'overrides' and 'arg_help'
        >>> parser = ArgumentParser(description="my arg parser")
        >>> add_arguments(
        ...     parser, 'verbose', 'quiet', 'nodefile',
        ...     set_defaults=True, overrides=dict(quiet=True, something=123)
        ...     arg_help=dict(nodefile="The file to output filtered nodes to")
        ... )
    
    
    :param ArgumentParser parser: A :class:`.ArgumentParser` instance
    :param overrides: A dict of arguments containing any additional defaults to add, or pre-existing defaults from :func:`.get_arg_default`
                      to override (replace).
    :param str arg_names: A list of names for parser arguments (see :attr:`.ARG_MAP`) to add to ``parser``, specified as
                          positional arguments
    :param bool set_defaults: (default: ``False``) If set to ``True``, will call :func:`.add_defaults_limit` after adding the requested
                              arguments, so that the appropriate default values for each of the arguments are set on ``parser``
    :param str arg_help: A mapping of argument names to help text to use instead of their defaults set in :attr:`.help_texts`.
    :return DictObject defs: If ``set_defaults`` was ``True``, then a :class:`.DictObject` containing the defaults which were set on
                             ``parser`` will be returned.
    :return List[str] defs: If ``set_defaults`` was ``False``, then a list of argument names which were considered "valid"
                            (contained within :attr:`.ARG_MAP`) will be returned.
    """
    clean_args, overrides = [], empty_if(overrides, {}, itr=True)
    for a in arg_names:
        if a not in ARG_MAP:
            log.debug("Skipping argument %s - not present in ARG_MAP", a)
            continue
        clean_args.append(a)
        if a in arg_help:
            ARG_MAP[a](parser, help_text=arg_help[a])
        else:
            ARG_MAP[a](parser)
    if set_defaults:
        return add_defaults_limit(parser, *clean_args, **overrides)
    return clean_args
    


