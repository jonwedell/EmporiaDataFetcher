#!/bin/bash

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

if [[ ! -d "${THIS_DIR}/venv" ]]; then
  python3 -m venv "${THIS_DIR}"/venv
  source "${THIS_DIR}"/venv/bin/activate
  pip3 install --upgrade pip wheel
  pip3 install -r "${THIS_DIR}"/requirements.txt
else
  source "${THIS_DIR}"/venv/bin/activate
  pip3 install --upgrade pip --quiet
  pip3 install -r "${THIS_DIR}"/requirements.txt --quiet
fi
