# zoneinfo.py - Compatibility shim for Python 3.8
import sys
import os
import importlib

if sys.version_info >= (3, 9):
    # Save the original sys.path and remove the current directory to allow importing the standard library module
    original_path = list(sys.path)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path = [p for p in sys.path if os.path.abspath(p) != current_dir and p != '']
    
    try:
        # Temporarily clear from sys.modules to avoid recursion
        if 'zoneinfo' in sys.modules:
            del sys.modules['zoneinfo']
        
        # Import the built-in standard library module
        _real_zoneinfo = importlib.import_module('zoneinfo')
        globals().update(_real_zoneinfo.__dict__)
        
        # Keep this module registered in sys.modules
        sys.modules['zoneinfo'] = sys.modules[__name__]
    finally:
        sys.path = original_path
else:
    # Try to import from backports.zoneinfo for Python 3.8
    try:
        from backports.zoneinfo import *
    except ImportError as e:
        raise ImportError(
            "backports.zoneinfo is required for zoneinfo support on Python < 3.9. "
            "Please run 'pip install backports.zoneinfo'."
        ) from e

