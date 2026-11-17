#!/bin/bash
# Run the Gym Tracker Python test suite (regression + feature tests).
set -e
cd "$(dirname "$0")/../app"
python3 -m pytest tests -q "$@"
