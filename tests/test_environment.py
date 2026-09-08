import os

import environment


def test_root_env_load_preserves_explicit_process_environment(monkeypatch, tmp_path):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "CHAT_SERVER_URL=ws://from-file:8000/\n"
        "DATABASE_URL=postgresql://from-file/test\n",
    )
    monkeypatch.setattr(environment, "ROOT_ENV_FILE", dotenv_path)
    monkeypatch.setenv("CHAT_SERVER_URL", "ws://from-shell:8000/")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert environment.load_root_env() is True
    assert os.environ["CHAT_SERVER_URL"] == "ws://from-shell:8000/"
    assert os.environ["DATABASE_URL"] == "postgresql://from-file/test"


def test_root_env_is_optional(monkeypatch, tmp_path):
    monkeypatch.setattr(environment, "ROOT_ENV_FILE", tmp_path / ".env")

    assert environment.load_root_env() is False
