import datetime as dt
import logging

import pytest
import requests

from inatel_sync.core import segredos
from inatel_sync.core.erros import ErroConfig, ErroRede
from inatel_sync.core.log import redigir
from inatel_sync.integracoes import moodle as M

ICS = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
    "BEGIN:VEVENT\r\nUID:1@moodle\r\nSUMMARY:Lista 3 &amp; 4 est\\, marcado(a) vence\r\n"
    "CATEGORIES:S05 - Interface Homem-Maquina\r\nDESCRIPTION:linha 1\\nlinha 2 com texto mui\r\n to longo\r\n"
    "DTSTART:20261110T025900Z\r\nDTEND:20261110T025900Z\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nUID:2@moodle\r\nSUMMARY:Semana de provas\r\nDTSTART;VALUE=DATE:20261116\r\n"
    "DTEND;VALUE=DATE:20261121\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nUID:3@moodle\r\nSUMMARY:Questionario is due\r\nCATEGORIES:C07B (2026)\r\n"
    "DTSTART;TZID=America/Sao_Paulo:20261112T235900\r\nEND:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


def test_parse_ics():
    evs = {e.chave: e for e in M.eventos_do_ics(ICS, "moodle|", "Moodle", "6")}
    prazo = evs["moodle|1@moodle"]
    assert prazo.titulo == "S05: Lista 3 & 4 est, marcado(a)"  # &amp; e \, desescapados; "vence" removido
    assert prazo.fim == dt.datetime(2026, 11, 9, 23, 59, tzinfo=prazo.fim.tzinfo)  # 02:59Z = 23:59 em SP
    assert prazo.fim - prazo.inicio == M.DURACAO_PRAZO and prazo.dia == dt.date(2026, 11, 9)
    assert "linha 1\nlinha 2 com texto muito longo" in prazo.descricao  # linha continuada desdobrada
    semana = evs["moodle|2@moodle"]
    assert semana.inicio is None and semana.dia == dt.date(2026, 11, 16) and semana.ultimo_dia == dt.date(2026, 11, 20)
    q = evs["moodle|3@moodle"]
    assert q.titulo == "C07B: Questionario" and q.fim.hour == 23 and q.fim.minute == 59


def test_url_valida_e_guardar():
    url = "https://moodle.inatel.br/calendar/export_execute.php?userid=1&authtoken=abc&preset_what=all"
    assert M.url_valida("moodle", url) and not M.url_valida("code", url)
    with pytest.raises(ErroConfig):
        M.guardar_url("moodle", "https://example.com")


class Resp:
    def __init__(self, status, texto=""):
        self.status_code, self.text, self.encoding = status, texto, None


def _com_url(monkeypatch):
    monkeypatch.setattr(segredos, "ler", lambda s, u: "https://moodle.inatel.br/calendar/export_execute.php?authtoken=SEGREDO")


def test_erros_nao_vazam_o_token(monkeypatch):
    _com_url(monkeypatch)
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(500))
    with pytest.raises(ErroRede) as e:
        M.baixar("moodle")
    assert "SEGREDO" not in str(e.value)

    def cai(*a, **k):
        raise requests.ConnectionError("Max retries exceeded with url: /calendar/export_execute.php?authtoken=SEGREDO")
    monkeypatch.setattr(requests, "get", cai)
    with pytest.raises(ErroRede) as e:
        M.baixar("moodle")
    assert "SEGREDO" not in str(e.value) and e.value.__cause__ is None


def test_html_de_erro_nao_e_calendario(monkeypatch):
    _com_url(monkeypatch)
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(200, "<html>login</html>"))
    with pytest.raises(ErroConfig):
        M.baixar("moodle")


def test_fonte_vazia_ou_com_erro_nao_libera_apagar(monkeypatch):
    cfg = {"moodle": {"ativo": True, "fontes": ["moodle", "code"], "cor": "laranja"}}
    textos = {"moodle": ICS, "code": "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"}
    monkeypatch.setattr(M, "baixar", lambda f: textos[f])
    monkeypatch.setattr(M, "hoje", lambda: dt.date(2026, 11, 1))
    c = M.Moodle(cfg).coletar()
    assert c.prefixos == ("moodle|",)  # Moodle Code veio vazio: os eventos dele ficam

    def falha(f):
        raise ErroRede("fora")
    monkeypatch.setattr(M, "baixar", falha)
    with pytest.raises(ErroRede):
        M.Moodle(cfg).coletar()


def test_redigir_log():
    texto = "GET /?state=abc&code=4/xyz&scope=x  url ...export_execute.php?userid=1&authtoken=deadbeef"
    limpo = redigir(texto)
    assert "abc" not in limpo and "4/xyz" not in limpo and "deadbeef" not in limpo
    assert "userid=1" in limpo


def test_log_redige_no_arquivo(tmp_path):
    from inatel_sync.core import log
    log.configurar(console=False)
    log.logger("moodle").warning("falhou %s", "https://x/?authtoken=SEGREDO")
    for h in logging.getLogger("inatel_sync").handlers:
        h.flush()
    from inatel_sync.core import paths
    conteudo = (paths.pasta_logs() / "sync.log").read_text(encoding="utf-8")
    assert "SEGREDO" not in conteudo and "[moodle] AVISO: falhou" in conteudo
    for h in list(logging.getLogger("inatel_sync").handlers):
        h.close()
        logging.getLogger("inatel_sync").removeHandler(h)
