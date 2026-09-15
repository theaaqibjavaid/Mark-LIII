"""Test configuration for MARK LIII action tests."""
import pytest
import sys
from pathlib import Path

# Add project root to path so actions can be imported
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
