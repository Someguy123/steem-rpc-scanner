#!/usr/bin/env python3
################################################################################
# This script is part of https://github.com/Someguy123/steem-rpc-scanner
#
# This is a very basic Python 3 script which shows how to easily call
# rpcscanner/health.py from a python script, and interpret it's return
# code to decide whether the node is working or not.
#
################################################################################
import subprocess
import re
from os.path import dirname, abspath, join

BOLD, RED, GREEN = '\033[1m', '\033[31m', '\033[32m'
RESET = '\033[39m'

# Absolute path to the folder ABOVE the folder containing this script (i.e. where the RPC scanner code is)
BASE_DIR = dirname(dirname(abspath(__file__)))

# Use regex to cleanly extract only valid URLs - ignore things like comments and broken URLs
RE_FIND_NODES = re.compile(r'^(https?://[a-zA-Z0-9./_:-]+).*?', re.MULTILINE)

# Open the nodes.txt file from the rpcscanner folder and read it into an array of lines
with open(join(BASE_DIR, 'nodes.txt')) as fp:
    _nodes = fp.read()

# Filter excess whitespace from each node line, remove blank lines, and remove commented nodes
nodes = RE_FIND_NODES.findall(_nodes)
nodes = [n.strip() for n in nodes if len(n.strip()) > 0]


# Very simple function which simply runs 'health.py scan (node)', sends it's stdout/stderr to /dev/null,
# then returns the exit code as an integer.
def test_node(node: str) -> int:
    p = subprocess.run(
        [join(BASE_DIR, 'health.py'), 'scan', node], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return p.returncode


# Test each node using health.py, print a green "UP NODE (node)" or red "DOWN NODE (node)" depending on whether
# the exit code was zero or not.
for n in nodes:
    rc = test_node(n)
    status = f"{BOLD}{GREEN}UP NODE" if rc == 0 else f"{BOLD}{RED}DOWN NODE"
    print(f"{status:<25}{RESET}{n}")

