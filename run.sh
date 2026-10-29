#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    echo "Chưa có .venv. Xem README.md để cài Python 3.11 và các thư viện."
    exit 1
fi
exec .venv/bin/python -m streamlit run app.py "$@"
