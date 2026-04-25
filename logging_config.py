"""
Logging configuration for the covenant extractor agent.

Default level: DEBUG (suitable for local development).
Override via the LOG_LEVEL environment variable:

    LOG_LEVEL=INFO python main.py credit_agreement.pdf   # production
    LOG_LEVEL=DEBUG python main.py credit_agreement.pdf  # explicit debug

Third-party libraries (pdfplumber, anthropic, pdfminer, etc.) are held at
WARNING so they don't drown out application logs.
"""

from __future__ import annotations

import logging
import os
import sys

# Loggers owned by this project — all others stay at WARNING.
_PROJECT_LOGGERS = ["agent", "main", "tools"]


def setup_logging() -> None:
    """Configure logging for the entire application. Call once at startup."""
    level_str = os.environ.get("LOG_LEVEL", "DEBUG").upper()
    level = getattr(logging, level_str, logging.DEBUG)

    # DEBUG format includes file + line number for easy navigation.
    # INFO and above use a shorter format.
    if level <= logging.DEBUG:
        fmt = "%(asctime)s [%(levelname)-8s] %(name)s:%(lineno)d - %(message)s"
    else:
        fmt = "%(asctime)s [%(levelname)-8s] %(name)s - %(message)s"

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))

    # Root at WARNING — silences pdfplumber, pdfminer, anthropic, httpx, etc.
    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    if not root.handlers:
        root.addHandler(handler)

    # Project loggers at the requested level.
    for name in _PROJECT_LOGGERS:
        lg = logging.getLogger(name)
        lg.setLevel(level)
        if not lg.handlers:
            lg.addHandler(handler)
        lg.propagate = False  # don't double-log through root
