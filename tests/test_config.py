import pytest

from trader.config import Secret, load_settings, parse_env_file


def test_parse_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('# comment\nTELEGRAM_BOT_TOKEN="abc:def"\nexport TELEGRAM_CHAT_ID=123\nEMPTY=\nNOEQUALS\n',
                        encoding="utf-8-sig")
    assert parse_env_file(env_file) == {"TELEGRAM_BOT_TOKEN": "abc:def", "TELEGRAM_CHAT_ID": "123", "EMPTY": ""}
    assert parse_env_file(tmp_path / "missing.env") == {}


def test_missing_credentials_turn_features_off_with_a_warning():
    settings = load_settings(env={})
    assert not settings.telegram_enabled and not settings.ai_enabled
    assert any("Telegram is off" in w for w in settings.warnings)


def test_credentials_enable_telegram_and_never_print_themselves():
    settings = load_settings(env={"TELEGRAM_BOT_TOKEN": "123:SECRETVALUE", "TELEGRAM_CHAT_ID": "42"})
    assert settings.telegram_enabled
    assert "SECRETVALUE" not in repr(settings) and "SECRETVALUE" not in f"{settings.telegram_bot_token}"
    assert settings.telegram_bot_token.reveal() == "123:SECRETVALUE"
    assert settings.secret_values() == ["123:SECRETVALUE"]
    assert not Secret("") and repr(Secret("x")) == "Secret('***')"


def test_ai_needs_the_flag_and_a_key(tmp_path):
    config = tmp_path / "settings.toml"
    config.write_text('[ai]\nenabled = true\nmodel = "some-model"\n', encoding="utf-8")
    assert not load_settings(env={}, settings_file=config).ai_enabled
    enabled = load_settings(env={"GEMINI_API_KEY": "k"}, settings_file=config)
    assert enabled.ai_enabled and enabled.ai_model == "some-model"


def test_ai_is_off_in_the_repository_config():
    assert not load_settings(env={"GEMINI_API_KEY": "k"}).ai_enabled


def test_data_provider_settings(tmp_path):
    default = load_settings(env={})
    assert default.data_provider == "yahoo" and default.max_data_delay_minutes == 20
    config = tmp_path / "settings.toml"
    config.write_text('[data]\nprovider = "kite"\n', encoding="utf-8")
    without_keys = load_settings(env={}, settings_file=config)
    assert without_keys.data_provider == "kite" and any("KITE_API_KEY" in w for w in without_keys.warnings)
    with_keys = load_settings(env={"KITE_API_KEY": "k", "KITE_API_SECRET": "s"}, settings_file=config)
    assert with_keys.secret_values() == ["k", "s"] and "'s'" not in repr(with_keys)
    config.write_text('[data]\nprovider = "bloomberg"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="provider"):
        load_settings(env={}, settings_file=config)


def test_real_environment_overrides_the_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("TELEGRAM_CHAT_ID=from_file\n", encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "from_environment")
    assert load_settings(env_file=env_file).telegram_chat_id == "from_environment"
