import datetime as dt

import httplib2
import pytest
import requests

from inatel_sync.core import config as C
from inatel_sync.core import estado, feriados
from inatel_sync.core.agendador import xml_tarefa
from inatel_sync.core.engine import Resumo
from inatel_sync.core.erros import ErroConfig, ErroRede, eh_erro_rede
from inatel_sync.core.executor import rodar
from inatel_sync.integracoes.base import Contexto


def test_config_padrao_valido_e_erros_claros(tmp_path):
    assert C.validar(C.carregar(exigir=False)) == []
    cfg = C.carregar(exigir=False)
    cfg["portal"].update(ativo=True, login="", curso="abc", fim_aulas="31/12", cor_aulas="dourado")
    erros = "\n".join(C.validar(cfg))
    assert "login vazio" in erros and "curso" in erros and "fim_aulas" in erros and "dourado" in erros


def test_config_ausente_e_toml_quebrado(tmp_path):
    with pytest.raises(ErroConfig, match="setup"):
        C.carregar(tmp_path / "nao.toml")
    ruim = tmp_path / "ruim.toml"
    ruim.write_text("[portal\nativo = ", encoding="utf-8")
    with pytest.raises(ErroConfig, match="invalido"):
        C.carregar(ruim)


def test_config_salvar_carregar_e_set(tmp_path):
    arq = tmp_path / "c.toml"
    cfg = C.carregar(exigir=False)
    assert C.definir(cfg, "outlook.dias", "30") == 30
    assert C.definir(cfg, "portal.sem_aula", "2026-11-03, 2026-11-04") == ["2026-11-03", "2026-11-04"]
    assert C.definir(cfg, "moodle.ativo", "sim") is True
    cfg["moodle"]["fontes"] = ["moodle"]
    C.salvar(cfg, arq)
    assert C.carregar(arq)["outlook"]["dias"] == 30
    with pytest.raises(ErroConfig):
        C.definir(cfg, "naoexiste", "1")


def test_feriados():
    assert feriados.pascoa(2026) == dt.date(2026, 4, 5)
    assert feriados.eh_feriado(dt.date(2026, 4, 3))  # Sexta-feira Santa
    assert feriados.eh_feriado(dt.date(2027, 3, 26))
    assert not feriados.eh_feriado(dt.date(2026, 11, 3))


def test_classifica_erro_de_rede():
    assert eh_erro_rede(requests.ConnectionError())
    assert eh_erro_rede(httplib2.ServerNotFoundError("www.googleapis.com"))
    try:
        try:
            raise ConnectionResetError(10054, "reset")
        except ConnectionResetError as e:
            raise RuntimeError("embrulhado") from e
    except RuntimeError as e:
        assert eh_erro_rede(e)
    assert not eh_erro_rede(KeyError("x"))


class Integ:
    def __init__(self, nome, faz):
        import logging
        self.nome, self.faz, self.log = nome, faz, logging.getLogger(f"inatel_sync.{nome}")

    def executar(self, ctx):
        return self.faz()


def _falha(exc):
    def f():
        raise exc
    return f


def test_executor_aviso_nao_e_erro_e_registra_estado():
    cfg = C.carregar(exigir=False)
    codigo = rodar([Integ("a", lambda: Resumo(criados=1)), Integ("b", _falha(ErroRede("GLPI fora de alcance"))),
                    Integ("c", _falha(requests.ConnectionError("x")))], Contexto(cfg))
    assert codigo == 0
    ex = estado.carregar()["execucoes"]
    assert ex["a"]["resultado"] == "ok" and ex["b"]["resultado"] == "aviso" and ex["c"]["resultado"] == "aviso"
    assert ex["b"]["ultimo_ok"] is None


def test_executor_acao_e_bug():
    cfg = C.carregar(exigir=False)
    assert rodar([Integ("a", _falha(ErroConfig("rode setup")))], Contexto(cfg)) == 2
    assert rodar([Integ("a", _falha(KeyError("bug"))), Integ("b", _falha(ErroConfig("x")))], Contexto(cfg)) == 1


def test_xml_da_tarefa():
    x = xml_tarefa("teste", "run portal", {"horarios": ["07:00", "18:00"]})
    assert x.count("<CalendarTrigger>") == 2 and "<StartWhenAvailable>true" in x and "IgnoreNew" in x
    y = xml_tarefa("t", "run outlook", {"a_cada_min": 30, "janela": ["07:00", "22:00"]})
    assert "<Interval>PT30M</Interval>" in y and "<Duration>PT900M</Duration>" in y
    z = xml_tarefa("t", "run all", {"logon": True})
    assert "<LogonTrigger>" in z and "<Delay>PT2M</Delay>" in z
