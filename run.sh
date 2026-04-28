#!/bin/bash
# Quick runner for testing scrapers locally before pushing to GitHub

PYTHONPATH=. python -m scheduler.runner "$@"
