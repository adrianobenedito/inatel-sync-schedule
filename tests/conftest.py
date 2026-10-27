import datetime as dt
import logging
from pathlib import Path

import pytest

from inatel_sync.core.tempo import TZ

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def pasta_limpa(tmp_path, monkeypatch):
    """Cada teste roda numa instalacao vazia: nada toca config, estado ou keyring reais."""
    monkeypatch.setenv("INATEL_SYNC_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("INATEL_SYNC_KEYRING_SUFIXO", "-pytest")


@pytest.fixture
def log():
    return logging.getLogger("inatel_sync.teste")


def html(nome):
    return (FIXTURES / nome).read_text(encoding="utf-8")


class AgendaFalsa:
    """Mesma interface da AgendaGoogle, em memoria."""

    def __init__(self, eventos=()):
        self.eventos = {e["id"]: e for e in eventos}
        self.aplicadas = []
        self._n = 0

    def listar(self, cal_id, desde, ate=None, tag="inatel-sync"):
        return [e for e in self.eventos.values()
                if e.get("extendedProperties", {}).get("private", {}).get("source") == tag]

    def aplicar(self, cal_id, ops, log):
        self.aplicadas += ops
        for op in ops:
            if op[0] == "inserir":
                self._n += 1
                self.eventos[f"novo{self._n}"] = dict(op[1], id=f"novo{self._n}")
            elif op[0] == "atualizar":
                self.eventos[op[1]] = dict(op[2], id=op[1])
            else:
                del self.eventos[op[1]]
        return 0


def dia(n):
    """Dias a partir de uma data fixa de referencia."""
    return dt.date(2026, 11, 2) + dt.timedelta(days=n)


AGORA = dt.datetime(2026, 11, 2, 12, 0, tzinfo=TZ)
