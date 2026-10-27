"""Tipos de falha: o que vira aviso de uma linha, o que pede acao da pessoa, o que e bug."""

import socket

from googleapiclient.errors import HttpError


class ErroInatelSync(Exception):
    pass


class Aviso(ErroInatelSync):
    """Falha esperada (rede, VPN, portal fora): uma linha no log, nada e apagado."""


class ErroRede(Aviso):
    pass


class PortalMudou(Aviso):
    """O HTML nao tem o formato esperado: melhor nao mexer na agenda."""


class AcaoNecessaria(ErroInatelSync):
    """So a pessoa resolve: reautorizar, cadastrar senha, corrigir config."""


class ErroAutorizacao(AcaoNecessaria):
    pass


class ErroConfig(AcaoNecessaria):
    pass


def _cadeia(exc):
    while exc is not None:
        yield exc
        exc = exc.__cause__ or exc.__context__


def eh_erro_rede(exc):
    """Queda de rede, DNS, timeout ou servidor fora (5xx/429), em qualquer ponto da cadeia de excecoes."""
    import requests
    import httplib2
    from google.auth.exceptions import TransportError

    tipos = (requests.ConnectionError, requests.Timeout, httplib2.HttpLib2Error, socket.gaierror,
             ConnectionError, TimeoutError, TransportError)
    for e in _cadeia(exc):
        if isinstance(e, tipos):
            return True
        if isinstance(e, HttpError) and (e.resp.status >= 500 or e.resp.status == 429):
            return True
        if isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code >= 500:
            return True
    return False


def resumo_rede(exc):
    """Mensagem curta, sem URL (o link do Moodle carrega token)."""
    for e in _cadeia(exc):
        if isinstance(e, HttpError):
            return f"o Google respondeu {e.resp.status}"
        resp = getattr(e, "response", None)
        if resp is not None and getattr(resp, "status_code", None):
            return f"o servidor respondeu {resp.status_code}"
    return type(exc).__name__
