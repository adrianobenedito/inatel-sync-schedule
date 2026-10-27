"""Onde ficam config, estado, logs e plugins da pessoa."""

import os
from pathlib import Path

NOME = "inatel-sync"


def pasta_dados():
    """%APPDATA%\\inatel-sync, ou INATEL_SYNC_HOME (instalacao de teste em pasta limpa)."""
    raiz = os.environ.get("INATEL_SYNC_HOME") or Path(os.environ.get("APPDATA") or Path.home()) / NOME
    p = Path(raiz)
    p.mkdir(parents=True, exist_ok=True)
    return p


def pasta_programa():
    """%LOCALAPPDATA%\\inatel-sync: venv e codigo instalados."""
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / NOME


def arquivo_config():
    return pasta_dados() / "config.toml"


def arquivo_estado():
    return pasta_dados() / "estado.json"


def pasta_logs():
    p = pasta_dados() / "logs"
    p.mkdir(exist_ok=True)
    return p


def pasta_plugins():
    return pasta_dados() / "plugins"


def client_secret():
    """O da pasta da pessoa tem prioridade sobre o que vem no pacote."""
    for p in (pasta_dados() / "client_secret.json", Path(__file__).resolve().parent.parent / "dados" / "client_secret.json"):
        if p.exists():
            return p
    return None
