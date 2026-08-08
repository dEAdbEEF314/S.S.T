import logging

from rich.console import Console

from sst.config import Config
from sst.main import setup_logging


def test_setup_logging_treats_log_messages_as_plain_text(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    console = Console(record=True)
    config = Config(steam_install_path="/tmp")

    setup_logging(config, console, is_dev=True)

    try:
        raise RuntimeError("closing tag '[/p]' at position 36 doesn't match")
    except RuntimeError as error:
        logging.getLogger("sst").error(
            f"致命的なシステムエラー: {error}", exc_info=True
        )

    output = console.export_text()
    assert "[/p]" in output