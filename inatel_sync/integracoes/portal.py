"""Portal Academico Inatel: Calendario de Provas e Quadro de Aulas (scraping do ASP.NET WebForms).

Login pela aba Graduacao > "Por Curso e Matricula": dropTipoAutenticacao=2, dropSubCurso = codigo do curso,
login = matricula (no Inatel costuma ser a matricula curta, sem o prefixo de curso e ano). Senha no keyring.
"""

import datetime as dt
import re
import time

import requests
from bs4 import BeautifulSoup

from inatel_sync.core import segredos
from inatel_sync.core.engine import Evento
from inatel_sync.core.erros import ErroConfig, ErroRede, PortalMudou
from inatel_sync.core.feriados import nacionais
from inatel_sync.core.tempo import TZ, hoje
from inatel_sync.integracoes.base import Coleta, Integracao

PORTAL = "https://siteseguro.inatel.br/PortalAcademico"
LOGIN_URL = PORTAL + "/WebLogin.aspx"
PROVAS_URL = PORTAL + "/Academico/Sra/WebListarHorariosProva.aspx?Visao=1"
AULAS_URL = PORTAL + "/Academico/Sra/WebQuadroAulas.aspx"
PROVAS_GRID = "ctl00_Corpo_UCCalendarioProvas1_GridDados"
AULAS_GRID = "ctl00_Corpo_UCQuadroHorarios1_GridDados"
LOGIN_PREFIX = "ctl00$Corpo$TabAcessoLogin$TabAluno$LogOn$"
TIPO_POR_CURSO = "2"
USER_AGENT = "Mozilla/5.0 (inatel-sync)"

PROVA_MINUTOS = 100  # um bloco de prova (19:30-21:10)
PROVA_LEMBRETES = [7 * 24 * 60, 24 * 60]  # 7 dias e 1 dia antes


class LoginRecusado(ErroConfig):
    pass


# ---------------------------------------------------------------- acesso

def _sessao():
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def _get(s, url):
    """Uma nova tentativa so (o portal as vezes derruba a conexao); nunca em loop."""
    for tentativa in (1, 2):
        try:
            r = s.get(url, timeout=60)
            r.raise_for_status()
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            if tentativa == 2:
                raise ErroRede("o Portal Academico nao respondeu") from e
            time.sleep(5)


def pagina_login(s=None):
    s = s or _sessao()
    return s, BeautifulSoup(_get(s, LOGIN_URL).text, "html.parser")


def _opcoes(soup, campo):
    sel = soup.find("select", attrs={"name": LOGIN_PREFIX + campo})
    return [(o.get("value", ""), o.get_text(" ", strip=True)) for o in sel.find_all("option")] if sel else []


def listar_cursos():
    """[(codigo, nome)] lidos do proprio formulario de login (usado pelo assistente)."""
    _, soup = pagina_login()
    cursos = [(v, n) for v, n in _opcoes(soup, "dropSubCurso") if v.strip() and v.strip() not in ("0", "-1")]
    if not cursos:
        raise PortalMudou("a lista de cursos nao apareceu na pagina de login do portal")
    return cursos


def entrar(login, curso, senha):
    """Sessao logada. LoginRecusado se o portal devolver o formulario de novo."""
    s, soup = pagina_login()
    botao = soup.find("input", {"name": LOGIN_PREFIX + "LoginButton"})
    if botao is None:
        raise PortalMudou("o formulario de login do portal mudou")
    form = {i["name"]: i.get("value", "") for i in soup.select("input[type=hidden]") if i.get("name")}
    form.update({
        "__EVENTTARGET": "", "__EVENTARGUMENT": "",
        LOGIN_PREFIX + "dropTipoAutenticacao": TIPO_POR_CURSO,
        LOGIN_PREFIX + "dropSubCurso": str(curso),
        LOGIN_PREFIX + "tbMatricula": str(login),
        LOGIN_PREFIX + "Password": senha,
        LOGIN_PREFIX + "LoginButton": botao.get("value", "Entrar"),
    })
    try:
        r = s.post(LOGIN_URL, data=form, timeout=60)
        r.raise_for_status()
    except (requests.ConnectionError, requests.Timeout) as e:
        raise ErroRede("o Portal Academico nao respondeu ao login") from e
    if "WebLogin.aspx" in r.url and LOGIN_PREFIX + "Password" in r.text:
        raise LoginRecusado("o portal recusou o login (matricula, curso ou senha incorretos). "
                            "Para trocar a senha: inatel-sync config senha")
    return s


def ler_grid(s, url, grid_id):
    r = _get(s, url)
    if "WebLogin.aspx" in r.url:
        raise ErroRede("a sessao do portal expirou no meio da leitura")
    grid = BeautifulSoup(r.text, "html.parser").find("table", id=grid_id)
    if grid is None:
        raise PortalMudou(f"a tabela {grid_id} nao apareceu no portal (o layout mudou?)")
    # As celulas do quadro de aulas tem tabelas internas: so as linhas do proprio grid interessam.
    linhas = []
    for tr in grid.find_all("tr"):
        if tr.find_parent("table") is not grid:
            continue
        linhas.append([" ".join(td.get_text(" ").split()) for td in tr.find_all(["td", "th"], recursive=False)])
    return linhas


# ---------------------------------------------------------------- parsing

def parse_provas(linhas, cor=None):
    if linhas and len(linhas[0]) < 7:
        raise PortalMudou(f"o calendario de provas veio com {len(linhas[0])} colunas (esperado 7)")
    provas, vistas = [], set()
    for row in linhas[1:]:
        if len(row) < 7 or not re.match(r"\d{2}/\d{2}/\d{4}$", row[1]):
            continue
        _, data, _, turma, prova, horario, local = row[:7]
        dia = dt.datetime.strptime(data, "%d/%m/%Y").date()
        chave = f"prova|{turma}|{prova}"
        if chave in vistas:
            chave += f"|{dia.isoformat()}"
        vistas.add(chave)
        inicio = None
        if re.match(r"\d{1,2}:\d{2}$", horario):
            h, m = map(int, horario.split(":"))
            inicio = dt.datetime.combine(dia, dt.time(h, m), TZ)
        titulo = prova if turma == "A Definir" else f"{turma} - {prova}"
        provas.append(Evento(
            chave=chave, titulo=f"Prova: {titulo}", dia=dia, inicio=inicio,
            fim=inicio + dt.timedelta(minutes=PROVA_MINUTOS) if inicio else None,
            local="" if local == "A Definir" else f"Inatel - {local}",
            descricao="Horario/local a definir pelo Inatel." if inicio is None else "",
            lembretes=list(PROVA_LEMBRETES), cor=cor,
        ))
    return provas


def parse_blocos(linhas):
    """Converte o quadro (linhas = horarios, colunas = dias) em blocos de aula continuos."""
    if not linhas:
        raise PortalMudou("o quadro de aulas veio vazio")
    # Colunas depois de "Horario": Segunda..Sabado, pela posicao (os acentos dos dias nem sempre chegam bem).
    cabecalho = linhas[0]
    slots = []
    for row in linhas[1:]:
        m = re.match(r"(\d{2}:\d{2}) - (\d{2}:\d{2})", row[0]) if row else None
        if m:
            slots.append((m.group(1), m.group(2), row[1:]))
    if len(linhas) > 1 and not slots:
        raise PortalMudou("o quadro de aulas nao tem linhas de horario no formato HH:MM - HH:MM")
    blocos = []
    for col in range(min(len(cabecalho) - 1, 6)):
        atual = None
        for ini, fim, cells in slots:
            cell = cells[col] if col < len(cells) else ""
            m = re.match(r"(.+?)\s*\(Local\s*:\s*(.+?)\)", cell)
            disc = local = None
            if m and "fixo" not in m.group(2):
                disc, local = m.group(1).strip(), m.group(2).strip()
            if atual and disc == atual["disc"] and local == atual["local"]:
                atual["fim"] = fim
                continue
            if atual:
                blocos.append(atual)
            atual = {"weekday": col, "disc": disc, "local": local, "ini": ini, "fim": fim} if disc else None
        if atual:
            blocos.append(atual)
    return blocos


def expandir_aulas(blocos, primeiro, ultimo, sem_aula=(), cor=None):
    pulados = set(sem_aula) | {d for ano in range(primeiro.year, ultimo.year + 1) for d in nacionais(ano)}
    aulas, dia = [], primeiro
    while dia <= ultimo:
        for b in blocos if dia not in pulados else []:
            if b["weekday"] != dia.weekday():
                continue
            h1, m1 = map(int, b["ini"].split(":"))
            h2, m2 = map(int, b["fim"].split(":"))
            aulas.append(Evento(
                chave=f"aula|{dia.isoformat()}|{b['ini']}|{b['disc']}", titulo=f"Aula: {b['disc']}", dia=dia,
                inicio=dt.datetime.combine(dia, dt.time(h1, m1), TZ), fim=dt.datetime.combine(dia, dt.time(h2, m2), TZ),
                local=f"Inatel - {b['local']}", cor=cor,
            ))
        dia += dt.timedelta(days=1)
    return aulas


def sem_conflito_com_provas(aulas, provas):
    """Tira as aulas que caem no horario de uma prova: no dia, a prova substitui a aula."""
    def conflita(a):
        return any(p.inicio and p.dia == a.dia and p.inicio < a.fim and a.inicio < p.fim for p in provas)
    return [a for a in aulas if not conflita(a)]


def fim_das_aulas(provas, fim_config, dia_hoje):
    """Data configurada; senao a ultima prova regular (antes das PVS), se ainda nao passou."""
    if fim_config:
        return dt.date.fromisoformat(fim_config)
    regulares = [p.dia for p in provas if "PVS" not in p.titulo]
    ultima = max(regulares) if regulares else None
    return ultima if ultima and ultima >= dia_hoje else None


# ---------------------------------------------------------------- integracao

class Portal(Integracao):
    nome = "portal"
    titulo = "Portal Inatel (provas e aulas)"
    prefixos = ("prova|", "aula|")

    def usuario_senha(self):
        return str(self.opcoes.get("matricula") or self.opcoes["login"])

    def coletar(self):
        senha = segredos.ler(segredos.PORTAL, self.usuario_senha())
        if not senha:
            raise ErroConfig("Senha do portal nao cadastrada. Rode: inatel-sync config senha")
        s = entrar(self.opcoes["login"], self.opcoes["curso"], senha)
        dia_hoje = hoje()
        # As provas sao lidas mesmo sem a integracao de provas: elas limitam e substituem as aulas.
        provas = parse_provas(ler_grid(s, PROVAS_URL, PROVAS_GRID), self.cor("cor_provas"))
        aulas, blocos, ultimo = [], [], None
        if self.opcoes.get("aulas", True):
            blocos = parse_blocos(ler_grid(s, AULAS_URL, AULAS_GRID))
            ultimo = fim_das_aulas(provas, self.opcoes.get("fim_aulas"), dia_hoje)
            if ultimo:
                sem_aula = {dt.date.fromisoformat(d) for d in self.opcoes.get("sem_aula", [])}
                aulas = sem_conflito_com_provas(
                    expandir_aulas(blocos, dia_hoje, ultimo, sem_aula, self.cor("cor_aulas")), provas)
            elif blocos:
                self.log.warning("Aulas pausadas: o portal ainda nao tem provas futuras para limitar o semestre. "
                                 "Defina o fim das aulas: inatel-sync config set portal.fim_aulas AAAA-MM-DD")
        self.log.info("Portal: %d provas, %d blocos de aula/semana, aulas ate %s", len(provas), len(blocos), ultimo)

        eventos, prefixos = [], []
        if self.opcoes.get("provas", True):
            eventos += [p for p in provas if p.dia >= dia_hoje]
            if provas:  # lista vazia pode ser o portal com problema: nao apaga as provas
                prefixos.append("prova|")
        eventos += aulas
        if aulas:
            prefixos.append("aula|")
        return Coleta(eventos, tuple(prefixos))
