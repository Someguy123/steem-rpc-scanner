# from dataclasses import dataclass

import logging
import sys
import re
from os.path import join, exists, isabs
from os import makedirs
from typing import List, Optional
from privex.loghelper import LogHelper
from rpcscanner import settings
from rpcscanner.settings import BASE_DIR, LOG_LEVEL, LOG_DIR, find_file

log = logging.getLogger(__name__)

if not exists(LOG_DIR):
    makedirs(LOG_DIR)


LOG_FORMATTER = logging.Formatter('[%(asctime)s]: %(name)-35s -> %(funcName)-20s : %(levelname)-8s:: %(message)s')


def clear_handlers(*loggers: Optional[str]):
    """Remove all log handlers (e.g. console, file) for a given logger name"""
    loggers = ['rpcscanner'] if len(loggers) == 0 else loggers
    
    for lg in loggers:
        lgr = logging.getLogger(lg)
        for h in lgr.handlers:
            lgr.removeHandler(h)
        lgr.handlers.clear()


def set_logging_level(level: int, *loggers: Optional[str], formatter=LOG_FORMATTER):
    lgs = []
    loggers = ['rpcscanner'] if len(loggers) == 0 else loggers
    level = logging.getLevelName(str(level).upper()) if isinstance(level, str) else level
    
    for lg in loggers:
        l_handler = LogHelper(lg, handler_level=level, formatter=formatter)
        l_handler.add_console_handler(level=level, stream=sys.stderr)
        lgs.append(l_handler)
    return lgs


def setup_loggers(*loggers, console=True, file_dbg=True, file_err=True):
    loggers = ['rpcscanner'] if len(loggers) == 0 else loggers
    
    for lg in loggers:
        _lh = LogHelper(lg, formatter=LOG_FORMATTER, handler_level=LOG_LEVEL)
        con, tfh_dbg, tfh_err = None, None, None
        if console: con = _lh.add_console_handler(level=LOG_LEVEL, stream=sys.stderr)
        if file_dbg:
            tfh_dbg = _lh.add_timed_file_handler(
                join(LOG_DIR, 'debug.log'), when='D', interval=1, backups=14, level=LOG_LEVEL
            )
        if file_err:
            tfh_err = _lh.add_timed_file_handler(
                join(LOG_DIR, 'error.log'), when='D', interval=1, backups=14, level=logging.WARNING
            )
        yield con, tfh_dbg, tfh_err, lg


con_handler, tfh_dbg_handler, tfh_err_handler, _ = list(setup_loggers())[0]


RE_FIND_NODES = re.compile(r'^(https?://[a-zA-Z0-9./_:-]+).*?', re.MULTILINE)
"""Regex to extract valid URLs which are at the start of lines"""


def load_nodes(file: str) -> List[str]:
    # nodes to be specified line by line. format: http://gtg.steem.house:8090
    npath = join(BASE_DIR, file) if not isabs(file) else file
    log.error("Loading nodes from full path: %s", npath)
    with open(npath, 'r') as fh:
        nodes = fh.read()
        node_list = RE_FIND_NODES.findall(nodes)
    return [n.strip() for n in node_list]


# Resolve settings.node_file into an absolute path
settings.node_file = find_file(settings.node_file, throw=False)

