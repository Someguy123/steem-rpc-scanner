#!/usr/bin/env bash
#############################################################################
#                                                                           #
#                     Production runner script for:                         #
#                                                                           #
#                        Hive/Steem RPC Scanner                             #
#                    (C) 2020 Someguy123.   GNU AGPL v3                     #
#                                                                           #
#      Someguy123 Blog: https://peakd.com/@someguy123                       #
#      Privex Site:     https://www.privex.io/                              #
#                                                                           #
#      Github Repo:     https://github.com/Someguy123/steem-rpc-scanner     #
#                                                                           #
#############################################################################

BOLD="" RED="" GREEN="" YELLOW="" BLUE="" MAGENTA="" CYAN="" WHITE="" RESET=""
if [ -t 1 ]; then BOLD="$(tput bold)" RED="$(tput setaf 1)" GREEN="$(tput setaf 2)" RESET="$(tput sgr0)"; fi

OUR_APP="Hive/Steem RPC Scanner" GH_REPO="https://github.com/Someguy123/steem-rpc-scanner"

# Error handling function for ShellCore
_sc_fail() { echo >&2 -e "\n${BOLD}${RED} [!!!] Failed to load or install Privex ShellCore...${RESET}\n\n" && exit 1; }

# Run ShellCore auto-install if we can't detect an existing ShellCore load.sh file.
[[ -f "${HOME}/.pv-shcore/load.sh" ]] || [[ -f "/usr/local/share/pv-shcore/load.sh" ]] ||
    {
        echo -e "${GREEN} >>> Auto-installing Privex ShellCore ( https://github.com/Privex/shell-core ) ...${RESET}"
        curl -fsS https://cdn.privex.io/github/shell-core/install.sh | bash >/dev/null
        echo -e "${BOLD}${GREEN} [+++] ShellCore successfully installed :)${RESET}"
    } || _sc_fail

# Attempt to load the local install of ShellCore first, then fallback to global install if it's not found.
[[ -d "${HOME}/.pv-shcore" ]] && source "${HOME}/.pv-shcore/load.sh" ||
    source "/usr/local/share/pv-shcore/load.sh" || _sc_fail

# Quietly automatically update Privex ShellCore every 14 days (default)
autoupdate_shellcore

######
# Directory where the script is located, so we can source files regardless of where PWD is
######

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:${PATH}"
export PATH="${HOME}/.local/bin:${PATH}"
export PYTHONUNBUFFERED=1 PIPENV_VERBOSITY=-1
cd "$DIR"

[[ -f .env ]] && source .env || true

# Override these defaults inside of `.env`
#: ${HOST='127.0.0.1'}
#: ${PORT='8484'}
#: ${GU_WORKERS='10'} # Number of Gunicorn worker processes

[[ -f "${DIR}/nodes.conf" ]] || {
    msgerr green " >> Copying example.nodes.conf -> nodes.conf"
    cp -v "${DIR}/example.nodes.conf" "${DIR}/nodes.conf"
}

case "$1" in
    health | HEALTH | check | CHECK)
        pipenv run ./health.py "${@:2}"
        exit $?
        ;;
    scan | SCAN | list | LIST | rpcs | RPCS | all | ALL)
        pipenv run ./app.py "${@:2}"
        exit $?
        ;;
        #    prod*)
        #        pipenv run hypercorn -b "${HOST}:${PORT}" -w "$GU_WORKERS" wsgi
        #        ;;
    update | upgrade)
        msg ts bold green " >> Updating files from Github"
        git pull
        msg ts bold green " >> Updating Python packages"
        pipenv update --ignore-pipfile
        msg ts bold green " +++ Finished"
        echo
        ;;
    install | setup | init)
        msg ts bold green " >> Updating files from Github"
        git pull
        msg ts bold green " >> Installing any missing packages"
        pkg_not_found python3 python3.8
        pkg_not_found python3 python3.7
        pkg_not_found python3 python3
        pkg_not_found pip3 python3.8-pip
        pkg_not_found pip3 python3.7-pip
        pkg_not_found pip3 python3-pip
        if not has_command pipenv; then
            PY_VER=""
            [ -z "$PY_VER" ] && has_binary python3.8 && PY_VER="python3.8" || true
            [ -z "$PY_VER" ] && has_binary python3.7 && PY_VER="python3.7" || true
            [ -z "$PY_VER" ] && PY_VER="python3" || true
            sudo -H "$PY_VER" -m pip install -U pipenv
        fi
        msg ts bold green " >> Creating virtualenv / Installing Python packages"
        pipenv install --ignore-pipfile
        [[ -f "${DIR}/nodes.conf" ]] || {
            msg ts green " >> Copying example.nodes.conf -> nodes.conf"
            cp -v "${DIR}/example.nodes.conf" "${DIR}/nodes.conf"
        }
        msg
        msg ts bold green " +++ Finished"
        echo
        ;;
    *)
        echo "Runner script for Someguy123's $OUR_APP"
        echo ""
        msg bold red "Unknown command.\n"
        msg bold green "$OUR_APP - (C) 2020 Someguy123 / Privex Inc."
        msg bold green "    Website: https://www.privex.io/ \n    Source: ${GH_REPO}\n"
        msg green "Available run.sh commands:\n"
        msg yellow "\t health [-q|-v] [scan|list] [-d] (rpc)          - Return health data for an individual RPC, " \
            "or all RPCs listed in the node list config file"
        msg yellow "\t scan|list [-q|-v|--plugins] [-f nodes.conf]    - Scan all RPCs in the node list config, " \
            "outputting their status information with a pretty printed colourful table."
        msg
        ;;
esac
