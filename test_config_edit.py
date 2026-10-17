"""Compatibility shim: the config_edit tests now live in tests/test_config_edit.py.

Usage: python test_config_edit.py        (full suite: python -m unittest discover -s tests -t .)
"""

import unittest

from tests.test_config_edit import ConfigEditTest  # noqa: F401

if __name__ == "__main__":
    unittest.main()
