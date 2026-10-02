import pytest

from data.seed.generate_synthetic_data import generate
from tools import operational_store


@pytest.fixture(autouse=True)
def fresh_databases():
    """Every test gets a freshly seeded analytics store and a clean
    operational store, so tests are independent and repeatable (design doc
    §11 CI/CD: golden-dataset / policy tests must be deterministic)."""
    generate()
    operational_store.reset()
    yield
