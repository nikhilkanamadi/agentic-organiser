from agents.demand import detect_anomaly


def test_hero_scenario_triggers_anomaly():
    result = detect_anomaly("P472", "ATL127")
    assert result["triggered"] is True
    # Seed data (data/seed/generate_synthetic_data.py) is engineered for ~+41.4%.
    assert 0.40 <= result["demand_change"] <= 0.43, (
        f"expected ~+41%, got {result['demand_change']:+.2%}"
    )


def test_flat_combo_does_not_trigger():
    result = detect_anomaly("P472", "NYC045")
    assert result["triggered"] is False
    assert abs(result["demand_change"]) < 0.05
