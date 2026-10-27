import datetime as dt

import pytest
from bs4 import BeautifulSoup
from conftest import html

from inatel_sync.core.erros import PortalMudou
from inatel_sync.integracoes import portal as P


def linhas(nome, grid):
    t = BeautifulSoup(html(nome), "html.parser").find("table", id=grid)
    out = []
    for tr in t.find_all("tr"):
        if tr.find_parent("table") is t:
            out.append([" ".join(td.get_text(" ").split()) for td in tr.find_all(["td", "th"], recursive=False)])
    return out


@pytest.fixture
def provas():
    return P.parse_provas(linhas("provas.html", P.PROVAS_GRID), cor="11")


@pytest.fixture
def blocos():
    return P.parse_blocos(linhas("quadro.html", P.AULAS_GRID))


def test_provas(provas):
    assert len(provas) == 12
    p = provas[0]
    assert p.chave.startswith("prova|") and p.titulo.startswith("Prova: ")
    assert p.inicio.hour == 19 and (p.fim - p.inicio) == dt.timedelta(minutes=100)
    assert p.lembretes == [7 * 24 * 60, 24 * 60] and p.cor == "11"
    assert len({x.chave for x in provas}) == 12  # chaves unicas


def test_blocos_do_quadro(blocos):
    assert len(blocos) == 7
    assert all(0 <= b["weekday"] <= 5 and b["ini"] < b["fim"] for b in blocos)


def test_expansao_pula_feriado_nacional_e_sem_aula(blocos):
    ini, fim = dt.date(2026, 11, 1), dt.date(2026, 11, 30)
    aulas = P.expandir_aulas(blocos, ini, fim, sem_aula={dt.date(2026, 11, 3)})
    dias = {a.dia for a in aulas}
    assert dt.date(2026, 11, 2) not in dias  # Finados
    assert dt.date(2026, 11, 20) not in dias  # Consciencia Negra
    assert dt.date(2026, 11, 3) not in dias  # sem_aula do config
    assert all(a.chave == f"aula|{a.dia.isoformat()}|{a.inicio:%H:%M}|{a.titulo[6:]}" for a in aulas)


def test_virada_de_ano(blocos):
    aulas = P.expandir_aulas(blocos, dt.date(2026, 12, 28), dt.date(2027, 1, 5))
    assert dt.date(2027, 1, 1) not in {a.dia for a in aulas}


def test_prova_substitui_aula_no_mesmo_horario(provas, blocos):
    aulas = P.expandir_aulas(blocos, dt.date(2026, 11, 3), dt.date(2026, 12, 12))
    restantes = P.sem_conflito_com_provas(aulas, provas)
    for p in provas:
        if p.inicio:
            assert not any(a.dia == p.dia and a.inicio < p.fim and p.inicio < a.fim for a in restantes)
    assert len(restantes) < len(aulas)


def test_fim_das_aulas(provas):
    assert P.fim_das_aulas(provas, "2026-12-01", dt.date(2026, 11, 1)) == dt.date(2026, 12, 1)
    ultima = max(p.dia for p in provas if "PVS" not in p.titulo)
    assert P.fim_das_aulas(provas, "", dt.date(2026, 11, 1)) == ultima
    # comeco de semestre: so provas antigas -> sem limite (as aulas ficam pausadas, nao inventadas)
    assert P.fim_das_aulas(provas, "", ultima + dt.timedelta(days=1)) is None


def test_layout_mudou_vira_portal_mudou():
    with pytest.raises(PortalMudou):
        P.parse_provas([["a", "b", "c"]])
    with pytest.raises(PortalMudou):
        P.parse_blocos([["Horario", "Seg"], ["sem horario aqui", "x"]])


class Resp:
    def __init__(self, texto, url):
        self.text, self.url, self.status_code = texto, url, 200

    def raise_for_status(self):
        pass


class SessaoFalsa:
    def __init__(self, pos_login):
        self.headers, self.pos_login, self.enviado = {}, pos_login, None

    def get(self, url, timeout):
        return Resp(html("login.html"), P.LOGIN_URL)

    def post(self, url, data, timeout):
        self.enviado = data
        return self.pos_login


def test_cursos_vem_do_formulario(monkeypatch):
    monkeypatch.setattr(P, "_sessao", lambda: SessaoFalsa(None))
    cursos = dict(P.listar_cursos())
    assert len(cursos) == 12 and "Engenharia de Software" in cursos.values()


def test_login_recusado_e_aceito(monkeypatch):
    s = SessaoFalsa(Resp(html("login.html"), P.LOGIN_URL))
    monkeypatch.setattr(P, "_sessao", lambda: s)
    with pytest.raises(P.LoginRecusado):
        P.entrar("123", "43", "errada")
    assert s.enviado[P.LOGIN_PREFIX + "dropTipoAutenticacao"] == "2"
    assert s.enviado[P.LOGIN_PREFIX + "dropSubCurso"] == "43"
    s.pos_login = Resp("<html>bem-vindo</html>", P.PORTAL + "/Academico/Default.aspx")
    assert P.entrar("123", "43", "certa") is s
