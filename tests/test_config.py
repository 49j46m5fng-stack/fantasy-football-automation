import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT_DIR / "config.json"


def load_config() -> dict:
    """Load the project's JSON configuration."""
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def test_expected_leagues_exist() -> None:
    config = load_config()

    assert "goats" in config["leagues"]
    assert "doats" in config["leagues"]


def test_league_ids_are_strings() -> None:
    config = load_config()

    assert config["leagues"]["goats"]["league_id"] == "1400610465024839680"
    assert config["leagues"]["doats"]["league_id"] == "1400610568489947136"

    assert isinstance(config["leagues"]["goats"]["league_id"], str)
    assert isinstance(config["leagues"]["doats"]["league_id"], str)


def test_core_league_counts() -> None:
    config = load_config()

    goats = config["leagues"]["goats"]
    doats = config["leagues"]["doats"]

    assert goats["playoff_spots"] == 8
    assert goats["relegation_spots"] == 2
    assert doats["promotion_spots"] == 2


def test_analytics_thresholds_are_sensible() -> None:
    config = load_config()

    analytics = config["analytics"]

    assert 0 <= analytics["bust_threshold"] < 1
    assert analytics["boom_threshold"] > 1
    assert analytics["minimum_projection_for_ratio"] >= 0