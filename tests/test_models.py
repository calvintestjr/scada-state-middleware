"""Boundary validation tests — a typo'd baseline must fail at load, not at 2 a.m."""
import pytest
import yaml
from pydantic import ValidationError

from middleware.models import SiteBaseline

VALID = """
site: lab-a
ignition:
  gateway:
    base_url: "http://ignition:8088"
time_sync:
  ntp_server: pool.ntp.org
"""


def test_valid_baseline_loads():
    b = SiteBaseline.model_validate(yaml.safe_load(VALID))
    assert b.ignition.gateway.failure_threshold == 3  # sane default applied


def test_unknown_key_rejected():
    raw = yaml.safe_load(VALID)
    raw["ignition"]["gateway"]["pol_interval_s"] = 5  # typo of poll_interval_s
    with pytest.raises(ValidationError):
        SiteBaseline.model_validate(raw)


def test_bad_threshold_rejected():
    raw = yaml.safe_load(VALID)
    raw["time_sync"]["failure_threshold"] = 0
    with pytest.raises(ValidationError):
        SiteBaseline.model_validate(raw)


def test_repo_baseline_is_valid():
    with open("desired-state/sites/lab-a.yaml") as f:
        b = SiteBaseline.model_validate(yaml.safe_load(f))
    assert b.site == "lab-a"
    # M2 scenarios present but disabled until Thread 13 completes
    assert b.ignition.database_connections["SCADA"].enabled is False
