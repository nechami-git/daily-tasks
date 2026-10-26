import pytest


@pytest.fixture(autouse=True)
def clean_data(tmp_path, monkeypatch):
    """Every test gets an empty data folder and a fixed 'today'."""
    monkeypatch.setenv("DAILY_TASKS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DAILY_TASKS_TODAY", "2026-10-25")
    return tmp_path
