from astrafeed.config import Settings


def test_default_language_is_english(tmp_path):
    assert Settings.load(tmp_path / "missing.yaml").language == "en"


def test_yaml_and_environment_override(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text("language: ru\npoll_seconds: 99\n")
    monkeypatch.setenv("ASTRAFEED_LANGUAGE", "en")
    settings = Settings.load(path)
    assert settings.language == "en"
    assert settings.poll_seconds == 99


def test_quickstart_config_loads(tmp_path):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    path = tmp_path / "config.yaml"
    path.write_text((root / "config.example.yaml").read_text())
    settings = Settings.load(path)
    assert settings.language == "en"
    assert settings.channels
