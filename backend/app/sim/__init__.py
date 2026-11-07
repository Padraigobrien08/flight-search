"""Fare simulator with a known optimum, for exact-regret benchmarks. Network design: NETWORK.md."""

from app.sim.exhaustive import candidates, exhaustive_best
from app.sim.prices import UNBIASED_CACHE, SimConfig
from app.sim.simulator import FareSimulator

__all__ = ["FareSimulator", "SimConfig", "UNBIASED_CACHE", "candidates", "exhaustive_best"]
