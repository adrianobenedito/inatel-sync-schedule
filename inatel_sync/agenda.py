"""inatel-sync agenda add/remove: compromisso avulso no Google Agenda, para a pessoa, skills e plugins.

Com --chave e idempotente: chamar de novo com a mesma chave atualiza o evento em vez de duplicar.
Sem horario (--data) o evento e de dia inteiro. A tag e agenda-cli: os syncs nunca mexem nesses eventos.
"""

import datetime as dt

from inatel_sync.core import google
from inatel_sync.core.config import cor_id
from inatel_sync.core.engine import Evento, comparavel
from inatel_sync.core.google import TAG_CLI, executar
from inatel_sync.core.tempo import TZ

REPETIR = {"diario": "DAILY", "semanal": "WEEKLY", "mensal": "MONTHLY", "anual": "YEARLY"}


def _calendario(service, agenda, cfg):
    nome = (agenda or "principal").strip()
    apelidos = {"inatel": cfg["portal"]["agenda"], "trabalho": cfg["outlook"]["agenda"]}
    return google.id_da_agenda(service, apelidos.get(nome.lower(), nome))


def _hora(texto):
    return dt.datetime.strptime(texto, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)


def _buscar(service, cal_id, chave):
    # singleEvents=False: evento repetido vem inteiro, nao cada ocorrencia
    return executar(service.events().list(
        calendarId=cal_id, privateExtendedProperty=[f"source={TAG_CLI}", f"key={chave}"],
        singleEvents=False, showDeleted=False, maxResults=10,
    )).get("items", [])


def adicionar(cfg, titulo, data=None, inicio=None, fim=None, descricao="", local="", agenda="principal",
              chave=None, lembretes=(), cor=None, ate=None, repetir=None, dry_run=False):
    """Cria ou atualiza. data='AAAA-MM-DD' (dia inteiro; ate=ultimo dia) ou inicio/fim='AAAA-MM-DD HH:MM'."""
    service = google.servico_agenda()
    cal_id = _calendario(service, agenda, cfg)
    if inicio:
        ini = _hora(inicio)
        e = Evento(chave="", titulo=titulo, dia=ini.date(), inicio=ini, fim=_hora(fim) if fim else ini + dt.timedelta(hours=1))
    else:
        dia = dt.date.fromisoformat(data)
        e = Evento(chave="", titulo=titulo, dia=dia, ultimo_dia=dt.date.fromisoformat(ate) if ate else None)
    e.chave = chave or f"{e.dia.isoformat()}|{titulo}"
    e.local, e.descricao, e.lembretes, e.cor = local, descricao, list(lembretes), cor_id(cor) if cor else None
    body = e.corpo(tag=TAG_CLI)
    if repetir:  # repete a partir do primeiro dia, no mesmo dia da semana/mes
        body["recurrence"] = [f"RRULE:FREQ={REPETIR[repetir]}"]

    existentes = _buscar(service, cal_id, e.chave)
    if existentes:
        ev = existentes[0]
        if comparavel(ev) == comparavel(body) and ev.get("recurrence") == body.get("recurrence"):
            return "igual", ev
        if dry_run:
            return "atualizaria", ev
        return "atualizado", executar(service.events().update(calendarId=cal_id, eventId=ev["id"], body=body))
    if dry_run:
        return "criaria", body
    return "criado", executar(service.events().insert(calendarId=cal_id, body=body))


def remover(cfg, chave, agenda="principal", dry_run=False):
    service = google.servico_agenda()
    cal_id = _calendario(service, agenda, cfg)
    alvo = _buscar(service, cal_id, chave)
    for ev in alvo if not dry_run else []:
        executar(service.events().delete(calendarId=cal_id, eventId=ev["id"]))
    return len(alvo)
