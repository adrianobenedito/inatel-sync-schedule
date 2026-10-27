"""inatel-sync tarefas: Google Tasks (add/list/done/remove).

Com --chave e idempotente. O Tasks nao tem campo proprio para isso, entao a chave vai na ultima
linha das notas ("[chave: ...]"). O prazo do Tasks e so a data (o horario e ignorado).
"""

import datetime as dt
import re

from inatel_sync.core import google, log
from inatel_sync.core.google import executar

MARCA = re.compile(r"\n?\[chave: (.+?)\]\s*$")
_log = log.logger("tarefas")


def _lista(service, nome, criar=True):
    """Id da lista pelo nome; "principal" e a lista padrao. Cria a lista se nao existir."""
    if not nome or nome.lower() in ("principal", "padrao", "@default"):
        return "@default"
    for tl in _listas(service):
        if tl["title"].lower() == nome.lower():
            return tl["id"]
    if not criar:
        return None
    _log.info("Lista criada: %s", nome)
    return executar(service.tasklists().insert(body={"title": nome}))["id"]


def _listas(service):
    listas, token = [], None
    while True:
        resp = executar(service.tasklists().list(maxResults=100, pageToken=token))
        listas += resp.get("items", [])
        token = resp.get("nextPageToken")
        if not token:
            return listas


def _todas(service, lista_id, concluidas=True):
    tarefas, token = [], None
    while True:
        resp = executar(service.tasks().list(tasklist=lista_id, showCompleted=concluidas, showHidden=concluidas,
                                             maxResults=100, pageToken=token))
        tarefas += resp.get("items", [])
        token = resp.get("nextPageToken")
        if not token:
            return tarefas


def _buscar(service, lista_id, chave):
    return [t for t in _todas(service, lista_id) if (m := MARCA.search(t.get("notes", ""))) and m.group(1) == chave]


def adicionar(titulo, data=None, notas="", lista="principal", chave=None):
    """Cria ou atualiza a tarefa. data='AAAA-MM-DD' (opcional)."""
    service = google.servico_tarefas()
    lista_id = _lista(service, lista)
    body = {"title": titulo, "notes": notas}
    if data:
        body["due"] = dt.date.fromisoformat(data).isoformat() + "T00:00:00.000Z"
    if chave:
        body["notes"] = (notas + "\n" if notas else "") + f"[chave: {chave}]"
        existentes = _buscar(service, lista_id, chave)
        if existentes:
            t = existentes[0]
            if t.get("title") == body["title"] and t.get("notes", "") == body["notes"] and \
                    (t.get("due") or "")[:10] == (body.get("due") or "")[:10]:
                return "igual", t
            t.update(body)
            if not data:
                t.pop("due", None)
            return "atualizado", executar(service.tasks().update(tasklist=lista_id, task=t["id"], body=t))
    return "criado", executar(service.tasks().insert(tasklist=lista_id, body=body))


def concluir(chave=None, titulo=None, lista="principal"):
    service = google.servico_tarefas()
    lista_id = _lista(service, lista, criar=False)
    if not lista_id:
        return 0
    alvo = _buscar(service, lista_id, chave) if chave else \
        [t for t in _todas(service, lista_id, False) if t.get("title", "").lower() == (titulo or "").lower()]
    for t in alvo:
        executar(service.tasks().patch(tasklist=lista_id, task=t["id"], body={"status": "completed"}))
    return len(alvo)


def remover(chave, lista="principal"):
    service = google.servico_tarefas()
    lista_id = _lista(service, lista, criar=False)
    if not lista_id:
        return 0
    alvo = _buscar(service, lista_id, chave)
    for t in alvo:
        executar(service.tasks().delete(tasklist=lista_id, task=t["id"]))
    return len(alvo)


def pendentes(lista=None):
    """Tarefas abertas de uma lista (ou de todas): [(lista, titulo, prazo ou None, notas)], por prazo."""
    service = google.servico_tarefas()
    listas = _listas(service)
    if lista:
        listas = [tl for tl in listas if tl["title"].lower() == lista.lower()] or [{"id": "@default", "title": lista}]
    itens = [(tl["title"], t.get("title", ""), (t.get("due") or "")[:10] or None, MARCA.sub("", t.get("notes", "")))
             for tl in listas for t in _todas(service, tl["id"], False)]
    return sorted(itens, key=lambda i: (i[2] is None, i[2] or "", i[0]))
