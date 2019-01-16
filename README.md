# Steem node RPC scanner

by [@someguy123](https://steemit.com/@someguy123)

![Screenshot of RPC Scanner](https://i.imgur.com/B9EShPn.png)

A fast and easy to use Python script which scans [Steem](https://www.steem.io) RPC nodes
asynchronously using request-threads and Twisted's Reactor.

**Features:**

 - Colorized output for easy reading
 - Tests a node's reliability during data collection, with multiple retries on error
 - Reports the average response time, and average amount of retries needed for basic calls
 - Detects a node's Steem version
 - Show the node's last block number and block time
 - Can determine whether a node is using Jussi, or if it's a raw steemd node
 - Can scan a list of 10 nodes in as little as 20 seconds thanks to Twisted Reactor + request-threads 

Python 3.7.0 or higher recommended

# Install

```
git clone https://github.com/Someguy123/steem-rpc-scanner.git
cd steem-rpc-scanner
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
cp nodes.txt.example nodes.txt
```

# Usage

For most people, the defaults are fine, so you can simply run:

```
./app.py
```

Add or delete nodes from `nodes.txt` line-by-line as needed. You can comment out nodes by placing `#` at the start of the line.

Format: `https://steemd.privex.io` - can also specify a port in standard url format, e.g. `https://gtg.steem.house:8090`


Full usage information (for most up to date usage, use `./app.py --help`)

```
usage: app.py [-h] [-v] [-q] [-f NODEFILE]

Scan RPC nodes from a list of URLs to determine their last block, version,
reliability, and response time.

optional arguments:
  -h, --help   show this help message and exit
  -v           display debugging
  -q           only show warnings or worse
  -f NODEFILE  specify a custom file to read nodes from (default: nodes.txt)
```

# License

GNU AGPL 3.0

See file LICENSE