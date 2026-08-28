#!/bin/bash
# Double-click this file in Finder to start the tool.
#
# It moves to its own folder, checks Python is there, downloads the draw
# history the first time, and opens the app in your browser. Closing the
# Terminal window that appears stops it.

cd "$(dirname "$0")" || exit 1

echo "======================================================"
echo "  Lottery Pattern Search"
echo "======================================================"
echo

# --- Python ----------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is not installed yet."
    echo
    echo "Run this in Terminal, click Install when the box appears, then"
    echo "double-click this file again:"
    echo
    echo "    xcode-select --install"
    echo
    read -r -p "Press Return to close." _
    exit 1
fi

VERSION=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)
echo "Python $VERSION found."

# --- Draw history ----------------------------------------------------------
if [ ! -f data/lotto_draws.csv ]; then
    echo
    echo "First run — downloading the published draw history."
    echo "This takes a few seconds and only happens once."
    echo
    python3 -m lotterypatterns fetch
    echo
    if [ ! -f data/lotto_draws.csv ]; then
        echo "The download did not work, so the app will start with the sample"
        echo "data instead. Everything still runs; the numbers are just based on"
        echo "example draws rather than real ones."
        echo
    fi
else
    DRAWS=$(($(wc -l < data/lotto_draws.csv) - 1))
    echo "Draw history found: $DRAWS Lotto draws."
fi

# --- Go --------------------------------------------------------------------
echo
echo "Starting. Your browser should open in a moment."
echo "Leave this window open while you use it. Close it to stop."
echo

python3 -m lotterypatterns gui

echo
read -r -p "Stopped. Press Return to close this window." _
