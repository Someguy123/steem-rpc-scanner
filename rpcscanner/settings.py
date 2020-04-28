"""
The settings in this file will normally be overwritten by the CLI tool, from either
a .env file, or arguments passed on the CLI.
"""
verbose: bool = False
quiet: bool = False
plugins: bool = False
node_file: str = 'nodes.txt'
test_account: str = 'someguy123'
test_post: str = 'announcement-soft-fork-0-22-2-released-steem-in-a-box-update'
