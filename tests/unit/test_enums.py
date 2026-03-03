"""Unit tests for schema enums."""
import pytest
from igrid.schema.enums import ComputeTier, tier_from_tps

def test_tier_platinum(): assert tier_from_tps(65.0) == ComputeTier.PLATINUM
def test_tier_gold(): assert tier_from_tps(40.0) == ComputeTier.GOLD
def test_tier_gold_boundary(): assert tier_from_tps(30.0) == ComputeTier.GOLD
def test_tier_silver(): assert tier_from_tps(20.0) == ComputeTier.SILVER
def test_tier_bronze(): assert tier_from_tps(10.0) == ComputeTier.BRONZE
def test_tier_zero(): assert tier_from_tps(0.0) == ComputeTier.BRONZE
