"""Autorizacao do Google (token no keyring), clientes da API e resolucao das agendas pelo nome."""

import functools
import json

from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from inatel_sync.core import estado, log, paths, segredos
from inatel_sync.core.erros import ErroAutorizacao, ErroConfig, ErroRede
from inatel_sync.core.tempo import TZ_NAME

# So agenda e tarefas: nada alem disso e pedido.
ESCOPOS = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/tasks"]
TAG = "inatel-sync"  # eventos dos syncs
TAG_CLI = "agenda-cli"  # eventos do comando agenda (os syncs nunca mexem)
TENTATIVAS = 5  # backoff exponencial do proprio client em 429/5xx

_log = log.logger("google")


def executar(req):
    return req.execute(num_retries=TENTATIVAS)


def _salvar(creds):
    segredos.gravar(segredos.GOOGLE, "token", creds.to_json())


def tem_token():
    return bool(segredos.ler(segredos.GOOGLE, "token"))


@functools.cache
def credenciais():
    info = segredos.ler(segredos.GOOGLE, "token")
    if not info:
        raise ErroAutorizacao("Google nao autorizado. Rode: inatel-sync auth")
    creds = Credentials.from_authorized_user_info(json.loads(info))
    if creds.valid:
        return creds
    if not creds.refresh_token:
        raise ErroAutorizacao("Autorizacao do Google incompleta. Rode: inatel-sync auth")
    try:
        creds.refresh(Request())
    except RefreshError as e:
        motivo = "revogada ou expirada" if "invalid_grant" in str(e) else "recusada pelo Google"
        raise ErroAutorizacao(f"A autorizacao do Google foi {motivo}. Rode: inatel-sync auth") from None
    except TransportError as e:
        raise ErroRede("sem acesso ao Google para renovar a autorizacao") from e
    _salvar(creds)  # so grava quando renovou
    return creds


def autorizar(incluir_tarefas=True):
    """Abre o navegador para a pessoa autorizar e guarda o token no keyring."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    arquivo = paths.client_secret()
    if not arquivo:
        raise ErroConfig("client_secret.json nao encontrado (deveria vir no pacote). Reinstale o inatel-sync.")
    flow = InstalledAppFlow.from_client_secrets_file(str(arquivo), ESCOPOS if incluir_tarefas else ESCOPOS[:1])
    creds = flow.run_local_server(
        port=0, prompt="consent", authorization_prompt_message="",
        success_message="Pronto! Pode fechar esta aba e voltar para a janela do inatel-sync.",
    )
    _salvar(creds)
    credenciais.cache_clear()
    servico_agenda.cache_clear()
    servico_tarefas.cache_clear()
    return creds


def tem_escopo(escopo):
    return escopo in (credenciais().scopes or [])


@functools.cache
def servico_agenda():
    return build("calendar", "v3", credentials=credenciais(), cache_discovery=False)


@functools.cache
def servico_tarefas():
    if not tem_escopo("https://www.googleapis.com/auth/tasks"):
        raise ErroAutorizacao("A autorizacao do Google nao inclui o Tasks. Rode: inatel-sync auth")
    return build("tasks", "v1", credentials=credenciais(), cache_discovery=False)


# ---------------------------------------------------------------- agendas

def _listar_agendas(service):
    agendas, token = [], None
    while True:
        resp = executar(service.calendarList().list(pageToken=token, maxResults=250, minAccessRole="owner"))
        agendas += resp.get("items", [])
        token = resp.get("nextPageToken")
        if not token:
            return agendas


def _guardar_id(nome, cal_id):
    estado.atualizar(lambda est: est.setdefault("agendas", {}).__setitem__(nome, cal_id))


def esquecer_agenda(nome):
    estado.atualizar(lambda est: est.get("agendas", {}).pop(nome, None))


def id_da_agenda(service, nome, criar=True, conferir=False):
    """Id da agenda pelo nome. Usa o id guardado; se sumiu do Google (404), procura pelo nome antes de criar.

    Qualquer outro erro (rede, 429, 500) sobe: criar agenda num erro passageiro duplicaria tudo.
    """
    if nome.strip().lower() in ("principal", "primary"):
        return "primary"
    cal_id = estado.carregar().get("agendas", {}).get(nome)
    if cal_id and not conferir:
        return cal_id
    if cal_id:
        try:
            executar(service.calendars().get(calendarId=cal_id))
            return cal_id
        except HttpError as e:
            if e.resp.status not in (404, 410):
                raise
            _log.warning("A agenda %s nao existe mais no Google", nome)
    for c in _listar_agendas(service):
        if c.get("summary", "").strip().lower() == nome.strip().lower():
            _guardar_id(nome, c["id"])
            return c["id"]
    if not criar:
        raise ErroConfig(f"Agenda {nome!r} nao encontrada no Google")
    cal = executar(service.calendars().insert(body={"summary": nome, "timeZone": TZ_NAME}))
    _guardar_id(nome, cal["id"])
    _log.info("Agenda criada: %s", nome)
    return cal["id"]
