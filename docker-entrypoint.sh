#!/bin/sh
# One source of truth for the state path and mode.
#
# The HEALTHCHECK and the served process must read the SAME state file. When the
# healthcheck path was hardcoded, running the container with a different --state
# left the healthcheck inspecting an unrelated file: it reported unhealthy while
# the process was fine, and — worse — would have reported healthy off a stale
# sibling file while the process was dead. Both now derive from ASTRA_STATE.
#
# With no arguments the container serves. With arguments it runs that astra
# subcommand instead, so `docker run <image> doctor` still works.
set -eu

if [ "$#" -eq 0 ]; then
    exec astra serve --mode "${ASTRA_MODE:-observe}" --state "${ASTRA_STATE:-/app/state/observe.db}"
fi

exec astra "$@"
