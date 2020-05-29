#!/usr/bin/env bash
################################################################################
# This script is part of https://github.com/Someguy123/steem-rpc-scanner
#
# This is a very basic Bash script which shows how to easily call
# rpcscanner/health.py from a shell script, and interpret it's return
# code to decide whether the node is working or not.
#
################################################################################
BOLD="" RED="" GREEN="" YELLOW="" BLUE="" MAGENTA="" CYAN="" WHITE="" RESET=""
if [ -t 1 ]; then
    BOLD="$(tput bold)" RED="$(tput setaf 1)" GREEN="$(tput setaf 2)" YELLOW="$(tput setaf 3)" BLUE="$(tput setaf 4)"
    MAGENTA="$(tput setaf 5)" CYAN="$(tput setaf 6)" WHITE="$(tput setaf 7)" RESET="$(tput sgr0)"
fi

# directory where the script is located, so we can source files regardless of where PWD is
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# SCAN_DIR represents where the rpcscanner folder is. We default to 1 level above the folder containing this script.
: "${SCAN_DIR="$(cd "${DIR}/.." && pwd)"}"
: "${NODE_LIST="${SCAN_DIR}/nodes.conf"}"

# We set the PYTHONPATH to the basefolder of rpcscanner, this allows project-level python imports
# i.e. 'from rpcscanner.core import something' to work correctly.
export PYTHONPATH="${SCAN_DIR}"

# Read only valid URLs from nodes.conf into the array 'NODES' - ignore things like comments starting with #
mapfile -t NODES < <(sed -En 's/^(https?\:\/\/[a-zA-Z0-9./_:-]+).*/\1/p' "$NODE_LIST")

#NODES=(
#    "https://hived.privex.io" "https://rpc.ausbit.dev" "https://anyx.io"
#)

check_node() { "$SCAN_DIR"/health.py scan "$1"; }

node_is_healthy() { check_node "$1" &>/dev/null; }

for n in "${NODES[@]}"; do
    if node_is_healthy "$n"; then
        echo "${BOLD}${GREEN}UP NODE${RESET}      $n"
    else
        echo "${BOLD}${RED}DOWN NODE${RESET}    $n"
    fi
done
