# Hive / Steem-based RPC node scanner

by [@someguy123](https://peakd.com/@someguy123)

![Screenshot of RPC Scanner app.py](https://cdn.privex.io/github/rpc-scanner/rpcscanner_list_may2020.png)

A fast and easy to use Python script which scans [Hive](https://www.hive.io), [Steem](https://www.steem.io), 
 and other forks' RPC nodes asynchronously using [HTTPX](https://github.com/encode/httpx) and
 native Python AsyncIO.

**Features:**

 - Colorized output for easy reading
 - Tests a node's reliability during data collection, with multiple retries on error
 - Reports the average response time, and average amount of retries needed for basic calls
 - Detects a node's Blockchain version
 - Show the node's last block number and block time
 - Can determine whether a node is using Jussi, or if it's a raw `steemd` node
 - Can scan a list of 20 nodes in as little as 10 seconds thanks to native Python AsyncIO plus
   the [HTTPX AsyncIO requests library](https://github.com/encode/httpx)

Python 3.8.0 or higher strongly recommended

Python 3.7.x may or may not work

# Install

### Easy way

```sh
git clone https://github.com/Someguy123/steem-rpc-scanner.git
cd steem-rpc-scanner

./run.sh install
```

### Manual install (if the easy way isn't working)

```sh
# You may need to install the default python version for your distro, for newer python versions
# to work properly (e.g. 'pip' and 'venv' may only be available as python3-pip and python3-venv)
apt install -y python3 python3-dev 
apt install -y python3-pip python3-venv
# Python 3.8+ is recommended, if available on your system.
apt install -y python3.8 python3.8-dev
# If you don't have 3.8 available, python 3.7 may work.
apt install -y python3.7 python3.7-dev

# Install pipenv using the newest version of Python on your system
python3.8 -m pip install -U pipenv

# Clone the repo
git clone https://github.com/Someguy123/steem-rpc-scanner.git
cd steem-rpc-scanner
# Create a virtualenv + install dependencies using pipenv
pipenv install
# Activate the virtualenv
pipenv shell
# Copy the example nodes.conf file into nodes.conf
cp example.nodes.conf nodes.conf
```

# Usage

### Scan a list of nodes and output their health info as a colourful table

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

### Scan an individual node with UNIX return codes

![Screenshot of RPC Scanner health.py](https://cdn.privex.io/github/rpc-scanner/rpcscanner_health_may2020.png)

RPCScanner can easily be integrated with monitoring scripts by using `./health.py scan`, which returns a standard UNIX
error code based on whether that RPC is working properly or not.

**Example 1** - Scanning fully functioning RPC node

```

user@host ~/rpcscanner $ ./run.sh health -q scan "https://hived.privex.io/"

Node: http://hived.privex.io/
Status: PERFECT
Network: Hive
Version: 0.23.0
Block: 43810613
Time: 2020-05-29T00:30:24 (0:00:00 ago)
Plugins: 8 / 8
PluginList: ['condenser_api.get_followers', 'bridge.get_trending_topics', 'condenser_api.get_accounts', 'condenser_api.get_witness_by_account', 'condenser_api.get_blog', 'condenser_api.get_content', 'condenser_api.get_account_history', 'account_history_api.get_account_history']
PassedStages: 3 / 3
Retries: 0
Score: 50 (out of 50)

user@host ~/rpcscanner $ echo $?
0
```

As you can see, `hived.privex.io` got a perfect score of `20`, and thus it signalled the UNIX return code `0`, which means
"everything was okay". 

**Example 2** - Scanning a misbehaving RPC node

```
user@host ~/rpcscanner $ ./run.sh health -q scan "https://steemd.privex.io/"

Node: http://steemd.privex.io/
Status: BAD
Network: Steem
Version: error
Block: 43536277
Time: 2020-05-20T13:59:57 (8 days, 10:31:40 ago)
Plugins: 4 / 8
PluginList: ['condenser_api.get_account_history', 'condenser_api.get_witness_by_account', 'condenser_api.get_accounts', 'account_history_api.get_account_history']
PassedStages: 2 / 3
Retries: 0
Score: 2 (out of 50)

user@host ~/rpcscanner $ echo $?
8

```

Unfortunately, `steemd.privex.io` didn't do anywhere near as well as `hived.privex.io` - it scored a rather low `7 / 20`, with
only 4 of the 8 RPC calls working properly which were tested.

This resulted in `health.py` signalling return code `8` instead (non-zero), which tells a calling program / script that
something went wrong during execution of this script. 

In this case, `8` is the default setting for `BAD_RETURN_CODE`, giving a clear signal to the caller that it's trying to tell it
"the passed RPC node's score is below the threshold and you should stop using it!".

You can change the numeric return code used for both "good" and "bad" results from the individual node scanner by setting
`GOOD_RETURN_CODE` and/or `BAD_RETURN_CODE` respectively in `.env`:

```env
# There isn't much reason to change GOOD_RETURN_CODE from the default of 0. But the option is there if you want it.
GOOD_RETURN_CODE=0
# We can change BAD_RETURN_CODE from the default of 8, to 99 for example.
# Any integer value from 0 to 254 can generally be used.
BAD_RETURN_CODE=99

```

#### Making use of these return codes in an external script

![Screenshot of extras/check_nodes.sh and py_check_nodes.py running](https://i.imgur.com/cm4DPVN.png)

Included in the [extras folder of the repo](https://github.com/Someguy123/steem-rpc-scanner/tree/master/extras), are two
example scripts - one in plain old Bash (the default terminal shell of most Linux distro's and macOS), and a python script,
intended for use on Python 3.

Both scripts do effectively the same thing - they load `nodes.txt`, skipping any commented out nodes, then check whether each
one is fully functional or not by calling `health.py scan NODE`, and check for a non-zero return code. Then outputting
either a green `UP NODE      http://example.com` or a red `DOWN NODE    http://example.com`.

Pictured above is a screenshot of both the bash example, and the python example - running with the same node list, and same
version of this RPC Scanner.

Handling program return codes is generally going to be the easiest in **shell scripting languages**, including Bash - as most
shell scripting languages are built around the UNIX methodology - everything is a file, language syntax is really just executing
programs with arguments, and return codes from those programs power the logic syntax etc.

The most basic shell script would be a simple ``if`` call, using ``/path/to/health.py scan http://somenode`` as the ``if`` test.
Most shells such as Bash will read the return (exit) code of the program, treating 0 as "true" and everything else as "false".

#### Basic shell script example

```shell script
#!/usr/bin/env bash

if /opt/rpcscanner/health.py scan "https://hived.privex.io" &> /dev/null; then
    echo "hived.privex.io is UP :)"
else
    echo "hived.privex.io is DOWN!!!"
fi
``` 


# License

[GNU AGPL 3.0](https://github.com/Someguy123/steem-rpc-scanner/blob/master/LICENSE)

See file [LICENSE](https://github.com/Someguy123/steem-rpc-scanner/blob/master/LICENSE)

# Common environment settings

 - `RPC_TIMEOUT` (default: `3`) Amount of seconds to wait for a response from an RPC node before giving up.
 - `MAX_TRIES` (default: `3`) Maximum number of attempts to run each call against an RPC node. Note that this
   number includes the initial try - meaning that setting `MAX_TRIES=1` will disable automatic retries for RPC calls.
   
   DO NOT set this to `0` or the scanner will simply think all nodes are broken. Setting `MAX_TRIES=0` may however be useful
   if you need to simulate how an external application handles "DEAD" results from the scanner. 
 - `RETRY_DELAY` (default: `2.0`) Number of seconds to wait between retrying failed RPC calls. Can be a decimal number of seconds,
   e.g. `0.15` would result in a 150ms retry delay.
 - `PUB_PREFIX` (default: `STM`) The first 3 characters at the start of a public key on the network(s) you're testing. This
   is used by `rpcscanner.MethodTests.MethodTests` for thorough "plugin tests" which validate that an account's public
   keys look correct.
 - `GOOD_RETURN_CODE` (default: `0`) The integer exit code returned by certain parts of RPCScanner, e.g. `health.py scan [node]`
   when the given RPC node(s) are functioning fully.
 - `BAD_RETURN_CODE` (default: `0`) The integer exit code returned by certain parts of RPCScanner, e.g. `health.py scan [node]`
   when the given RPC node(s) are severely unstable or missing vital plugins.
