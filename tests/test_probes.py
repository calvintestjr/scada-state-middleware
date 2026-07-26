"""Probes must return structured Observations and never raise."""
import pytest

from middleware.collector.gateway_http import probe_gateway
from middleware.models import GatewayBaseline, ProbeStatus


@pytest.mark.asyncio
async def test_unreachable_gateway_returns_fail_not_exception():
    cfg = GatewayBaseline(base_url="http://127.0.0.1:9", timeout_ms=300)
    obs = await probe_gateway("lab-a", cfg)
    assert obs.status in (ProbeStatus.fail, ProbeStatus.error)
    assert obs.detail  # evidence recorded
