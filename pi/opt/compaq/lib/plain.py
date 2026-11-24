#!/usr/bin/env python3
"""Filters text to plain ASCII for the Compaq: curly quotes, dashes and
accents become their ASCII look-alikes (the same rules as chat.py).
Usage: some-program | plain.py"""

import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chat import to_ascii  # noqa: E402

signal.signal(signal.SIGPIPE, signal.SIG_DFL)     # (the pager closed early: just stop)
sys.stdout.write(to_ascii(sys.stdin.read()))
