"""
ThirdPartyChaos -- Module 5: Test Verifier -- fixtures
"""
import time
import pytest
import requests

CONTROL_API = "http://localhost:9000"
SAMPLE_APP  = "http://localhost:3000"


@pytest.fixture(autouse=True)
def clear_fault_before_each():
    """Always clear any active fault before and after each test."""
    try:
        requests.post(f"{CONTROL_API}/chaos/clear", timeout=3)
    except Exception:
        pass
    yield
    try:
        requests.post(f"{CONTROL_API}/chaos/clear", timeout=3)
    except Exception:
        pass


@pytest.fixture
def activate_fault():
    """Factory fixture: activate a named fault for the test duration."""
    def _activate(fault_name: str):
        resp = requests.post(
            f"{CONTROL_API}/chaos/set/{fault_name}", timeout=3
        )
        assert resp.status_code == 200, \
            f"Could not activate fault '{fault_name}': {resp.text}"
        time.sleep(0.3)   # brief settle time
    return _activate
