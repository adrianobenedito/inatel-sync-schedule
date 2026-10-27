"""Engine unica de sincronizacao: diff por chave entre o que a fonte tem e o que esta no Google.

Regras que protegem a agenda:
- cada integracao so apaga eventos com os proprios prefixos de chave (nunca os de outra);
- so apaga eventos que ainda nao comecaram;
- se for apagar mais que o limite da trava, nao apaga nada e avisa (passa so com --forcar);
- eventos sem a tag inatel-sync (criados a mao ou pelo comando agenda) nunca sao tocados.
"""

import datetime as dt
from dataclasses import dataclass, field

from googleapiclient.errors import HttpError

from inatel_sync.core.google import TAG, executar
from inatel_sync.core.tempo import TZ, TZ_NAME, agora as _agora

TAM_LOTE = 50  # maximo recomendado pelo Google por batch


@dataclass
class Evento:
    chave: str
    titulo: str
    dia: dt.date
    inicio: dt.datetime | None = None  # None = dia inteiro
    fim: dt.datetime | None = None
    ultimo_dia: dt.date | None = None  # dia inteiro com varios dias
    local: str = ""
    descricao: str = ""
    lembretes: list = field(default_factory=list)
    cor: str | None = None

    def corpo(self, tag=TAG):
        body = {
            "summary": self.titulo,
            "location": self.local,
            "description": self.descricao,
            "reminders": {"useDefault": False,
                          "overrides": [{"method": "popup", "minutes": m} for m in self.lembretes]},
            "extendedProperties": {"private": {"source": tag, "key": self.chave}},
        }
        if self.inicio:
            body["start"] = {"dateTime": self.inicio.isoformat(), "timeZone": TZ_NAME}
            body["end"] = {"dateTime": self.fim.isoformat(), "timeZone": TZ_NAME}
        else:
            body["start"] = {"date": self.dia.isoformat()}
            body["end"] = {"date": ((self.ultimo_dia or self.dia) + dt.timedelta(days=1)).isoformat()}
        if self.cor:
            body["colorId"] = self.cor
        return body


@dataclass
class Resumo:
    criados: int = 0
    atualizados: int = 0
    removidos: int = 0
    retidos: int = 0  # seguraria pela trava
    falhas: int = 0

    def texto(self, dry_run=False):
        t = f"{self.criados} criados, {self.atualizados} atualizados, {self.removidos} removidos"
        if self.retidos:
            t += f", {self.retidos} retidos pela trava"
        if self.falhas:
            t += f", {self.falhas} falharam"
        return t + (" (simulacao)" if dry_run else "")


def comparavel(ev):
    """O que importa para decidir se o evento mudou (o Google devolve campos a mais)."""
    def quando(x):
        if "dateTime" in x:
            return dt.datetime.fromisoformat(x["dateTime"]).astimezone(TZ).isoformat()
        return x.get("date")
    rem = ev.get("reminders", {})
    return (
        ev.get("summary", ""), ev.get("location", ""), ev.get("description", ""),
        quando(ev["start"]), quando(ev["end"]),
        tuple(sorted(o["minutes"] for o in rem.get("overrides", []))),
        ev.get("colorId"),
    )


def _chave(ev):
    return ev.get("extendedProperties", {}).get("private", {}).get("key", "")


def _ainda_nao_comecou(ev, agora):
    ini = ev["start"]
    if "dateTime" in ini:
        return dt.datetime.fromisoformat(ini["dateTime"]) > agora
    return dt.date.fromisoformat(ini["date"]) >= agora.date()


def _dia(ev):
    return ev["start"].get("dateTime", ev["start"].get("date", ""))[:10]


class AgendaGoogle:
    """Acesso ao Google usado pela engine (nos testes entra um falso com a mesma interface)."""

    CAMPOS = ("nextPageToken,items(id,status,summary,location,description,start,end,"
              "reminders,colorId,extendedProperties,recurringEventId)")

    def __init__(self, service):
        self.service = service

    def listar(self, cal_id, desde, ate=None, tag=TAG):
        eventos, token = [], None
        while True:
            resp = executar(self.service.events().list(
                calendarId=cal_id, timeMin=desde.isoformat(), timeMax=ate.isoformat() if ate else None,
                singleEvents=True, privateExtendedProperty=f"source={tag}", maxResults=2500,
                pageToken=token, fields=self.CAMPOS,
            ))
            eventos += resp.get("items", [])
            token = resp.get("nextPageToken")
            if not token:
                return eventos

    def aplicar(self, cal_id, operacoes, log):
        """Aplica em lotes de 50; o que falhar no lote e tentado de novo sozinho (com backoff). Devolve n de falhas."""
        evs = self.service.events()
        pedidos = []
        for op in operacoes:
            if op[0] == "inserir":
                pedidos.append(evs.insert(calendarId=cal_id, body=op[1]))
            elif op[0] == "atualizar":
                pedidos.append(evs.update(calendarId=cal_id, eventId=op[1], body=op[2]))
            else:
                pedidos.append(evs.delete(calendarId=cal_id, eventId=op[1]))
        repetir = []
        for i in range(0, len(pedidos), TAM_LOTE):
            lote = self.service.new_batch_http_request()
            for j, p in enumerate(pedidos[i:i + TAM_LOTE], start=i):
                lote.add(p, request_id=str(j), callback=lambda rid, _resp, exc: exc and repetir.append(int(rid)))
            lote.execute()
        falhas = 0
        for j in repetir:
            try:
                executar(pedidos[j])
            except HttpError as e:
                if operacoes[j][0] == "apagar" and e.resp.status in (404, 410):
                    continue  # ja tinha sido apagado
                falhas += 1
                log.error("Google recusou %s (%s): %s", operacoes[j][0], e.resp.status, e.reason)
        return falhas


def sincronizar(api, cal_id, desejados, prefixos, desde, *, ate=None, dry_run=False, forcar=False,
                limite=(5, 30), nome="", log, agora=None):
    """Deixa a agenda igual a `desejados` para as chaves com `prefixos`, no intervalo [desde, ate)."""
    agora = agora or _agora()
    resumo = Resumo()
    if not prefixos:
        log.info("Nada a sincronizar (fonte sem dados confiaveis nesta execucao)")
        return resumo

    atuais, duplicados = {}, []
    for ev in api.listar(cal_id, desde, ate):
        chave = _chave(ev)
        if not chave.startswith(tuple(prefixos)):
            continue
        if chave in atuais:
            duplicados.append(ev)  # copia com a mesma chave: fica uma so
        else:
            atuais[chave] = ev

    desejados = {e.chave: e for e in desejados if e.chave.startswith(tuple(prefixos))}
    ops = []
    for chave, e in desejados.items():
        corpo = e.corpo()
        ev = atuais.get(chave)
        if ev is None:
            log.info("+ %s %s", e.dia, e.titulo)
            ops.append(("inserir", corpo))
            resumo.criados += 1
        elif comparavel(ev) != comparavel(corpo):
            log.info("~ %s %s", e.dia, e.titulo)
            ops.append(("atualizar", ev["id"], corpo))
            resumo.atualizados += 1

    apagar = [ev for chave, ev in atuais.items() if chave not in desejados and _ainda_nao_comecou(ev, agora)]
    apagar += duplicados
    max_n, max_pct = limite
    if apagar and not forcar and len(apagar) > max_n and len(apagar) * 100 > max_pct * max(len(atuais), 1):
        log.warning("Trava de seguranca: iria apagar %d de %d eventos; nada foi apagado. "
                    "Se estiver certo, rode: inatel-sync run %s --forcar", len(apagar), len(atuais), nome)
        resumo.retidos = len(apagar)
        apagar = []
    for ev in apagar:
        log.info("- %s %s", _dia(ev), ev.get("summary"))
        ops.append(("apagar", ev["id"]))
        resumo.removidos += 1

    if ops and not dry_run:
        resumo.falhas = api.aplicar(cal_id, ops, log)
    log.info("Resumo: %s", resumo.texto(dry_run))
    return resumo
