"""Moodle Inatel e Moodle Code: export iCal do calendario (entregas, questionarios...).

O link de exportacao tem um token pessoal, entao fica no keyring, nunca no config ou no log.
Onde pegar: Moodle > Calendario > Exportar calendario > Todos os eventos + Intervalo personalizado >
Obter URL do calendario > Copiar URL.
"""

import datetime as dt
import html
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from inatel_sync.core import segredos
from inatel_sync.core.engine import Evento
from inatel_sync.core.erros import ErroConfig, ErroRede
from inatel_sync.core.tempo import TZ, hoje
from inatel_sync.integracoes.base import Coleta, Integracao

# fonte: (usuario no keyring, host, prefixo da chave, local do evento)
FONTES = {
    "moodle": ("ical", "moodle.inatel.br", "moodle|", "Moodle"),
    "code": ("ical-code", "moodle-code.inatel.br", "moodlecode|", "Moodle Code"),
}
LEMBRETES = [24 * 60, 3 * 60]  # 1 dia e 3 horas antes
DURACAO_PRAZO = dt.timedelta(minutes=30)  # prazo vira um bloco que termina na hora da entrega
MAX_DESCRICAO = 3000


def url_valida(fonte, url):
    host = FONTES[fonte][1]
    return f"//{host}/calendar/export_execute.php" in url and "authtoken=" in url


def guardar_url(fonte, url):
    url = url.strip()
    if not url_valida(fonte, url):
        raise ErroConfig(f"isso nao e o link de exportacao de {FONTES[fonte][1]} (copie o URL do calendario)")
    segredos.gravar(segredos.MOODLE, FONTES[fonte][0], url)


def desescapar(v):
    v = re.sub(r"\\([\\;,nN])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), v)
    return html.unescape(v)  # o Moodle manda o titulo com entidades HTML (&amp;)


def ler_ics(texto):
    """Parser minimo de iCal: lista de dicts {PROPRIEDADE: (params, valor)} por VEVENT."""
    linhas = re.sub(r"\r?\n[ \t]", "", texto).splitlines()  # desdobra linhas continuadas
    eventos, atual = [], None
    for linha in linhas:
        if linha == "BEGIN:VEVENT":
            atual = {}
        elif linha == "END:VEVENT":
            if atual is not None:
                eventos.append(atual)
            atual = None
        elif atual is not None and ":" in linha:
            nome, valor = linha.split(":", 1)
            nome, _, params = nome.partition(";")
            atual[nome.upper()] = (params, valor)
    return eventos


def quando(prop):
    params, valor = prop
    if "VALUE=DATE" in params.upper() or len(valor) == 8:
        return dt.date(int(valor[:4]), int(valor[4:6]), int(valor[6:8]))
    t = dt.datetime.strptime(valor.rstrip("Z"), "%Y%m%dT%H%M%S")
    if valor.endswith("Z"):
        return t.replace(tzinfo=dt.timezone.utc).astimezone(TZ)
    tz = TZ
    m = re.search(r"TZID=([^;]+)", params)
    if m:
        try:
            tz = ZoneInfo(m.group(1).strip('"'))
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return t.replace(tzinfo=tz).astimezone(TZ)


def eventos_do_ics(texto, prefixo, local, cor):
    itens = []
    for ev in ler_ics(texto):
        if "DTSTART" not in ev:
            continue
        titulo = desescapar(ev.get("SUMMARY", ("", "(sem titulo)"))[1])
        titulo = re.sub(r"\s+(está|esta) marcad[oa]\(a\) para esta data$|\s+(vence|deve ser entregue)$"
                        r"|\s+(submission )?is due$", "", titulo)
        curso = desescapar(ev.get("CATEGORIES", ("", ""))[1])
        descricao = desescapar(ev.get("DESCRIPTION", ("", ""))[1]).strip()
        descricao = "\n\n".join(p for p in (curso, descricao) if p)[:MAX_DESCRICAO]
        inicio = quando(ev["DTSTART"])
        fim = quando(ev["DTEND"]) if "DTEND" in ev else inicio
        e = Evento(
            chave=prefixo + ev.get("UID", ("", titulo + str(inicio)))[1],
            titulo=f"{re.split(r' - | [(]', curso)[0]}: {titulo}" if curso else titulo,  # "S05: ...", "C07B: ..."
            dia=inicio if isinstance(inicio, dt.date) and not isinstance(inicio, dt.datetime) else inicio.date(),
            local=local, descricao=descricao, lembretes=list(LEMBRETES), cor=cor,
        )
        if isinstance(inicio, dt.datetime):
            if fim <= inicio:  # prazo (inicio = fim): bloco curto terminando na hora da entrega
                inicio, fim = inicio - DURACAO_PRAZO, inicio
            e.dia, e.inicio, e.fim = fim.date(), inicio, fim
        else:
            e.ultimo_dia = (fim - dt.timedelta(days=1)) if fim > inicio else inicio
        itens.append(e)
    return itens


def baixar(fonte):
    usuario, host, _, _ = FONTES[fonte]
    url = segredos.ler(segredos.MOODLE, usuario)
    if not url:
        raise ErroConfig(f"Link de {host} nao cadastrado. Rode: inatel-sync config moodle-url {fonte}")
    try:
        r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0 (inatel-sync)"})
    except (requests.ConnectionError, requests.Timeout) as e:
        raise ErroRede(f"{host} nao respondeu") from None
    if r.status_code >= 400:
        raise ErroRede(f"{host} respondeu {r.status_code}")  # sem a URL: ela carrega o token
    r.encoding = "utf-8"
    if "BEGIN:VCALENDAR" not in r.text:
        raise ErroConfig(f"{host} nao devolveu um calendario (o link mudou? rode: inatel-sync config moodle-url {fonte})")
    return r.text


class Moodle(Integracao):
    nome = "moodle"
    titulo = "Moodle e Moodle Code (entregas)"
    prefixos = tuple(f[2] for f in FONTES.values())

    def coletar(self):
        dia_hoje = hoje()
        eventos, prefixos, falhas = [], [], []
        for fonte in self.opcoes.get("fontes", []):
            _, host, prefixo, local = FONTES[fonte]
            try:
                itens = eventos_do_ics(baixar(fonte), prefixo, local, self.cor())
            except (ErroRede, ErroConfig) as e:
                # Um Moodle fora nao impede o outro; os eventos dele ficam como estao.
                self.log.warning("%s; os eventos dele ficam como estao", e)
                falhas.append(e)
                continue
            futuros = [i for i in itens if (i.ultimo_dia or i.dia) >= dia_hoje]
            self.log.info("%s: %d eventos no calendario, %d de hoje em diante", host, len(itens), len(futuros))
            eventos += futuros
            if itens:  # calendario vazio pode ser erro do Moodle: nao apaga
                prefixos.append(prefixo)
        if falhas and len(falhas) == len(self.opcoes.get("fontes", [])):
            raise falhas[0]
        return Coleta(eventos, tuple(prefixos))
