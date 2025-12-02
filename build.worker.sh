#!/usr/bin/env bash
# Build script for worker service deployment on Railway

set -o errexit

pip install -r requirements.worker.txt
