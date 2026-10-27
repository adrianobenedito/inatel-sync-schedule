"""Log rotativo: sync.log com uma linha por evento relevante, debug.log com os detalhes (tracebacks)."""

import logging
import re
import sys
from logging.handlers import RotatingFileHandler

from inatel_sync.core import paths

RAIZ = "inatel_sync"
# Links do Moodle, codigo do OAuth, tokens: nunca vao para o log.
_SEGREDO = re.compile(r"(authtoken|access_token|refresh_token|token|code|state|client_secret|password|senha)=([^&\s\"',]+)", re.I)


def redigir(texto):
    return _SEGREDO.sub(r"\1=***", texto)


class _Redige(logging.Filter):
    def filter(self, record):
        record.msg = redigir(record.getMessage())
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = redigir(logging.Formatter().formatException(record.exc_info))
        record.modulo = record.name.rsplit(".", 1)[-1] if record.name != RAIZ else "geral"
        return True


class _Formato(logging.Formatter):
    NIVEL = {logging.WARNING: "AVISO: ", logging.ERROR: "ERRO: ", logging.CRITICAL: "ERRO: "}

    def format(self, record):
        record.nivel = self.NIVEL.get(record.levelno, "")
        return super().format(record)


def logger(modulo=None):
    return logging.getLogger(f"{RAIZ}.{modulo}" if modulo else RAIZ)


def configurar(console=True, verbose=False):
    raiz = logging.getLogger(RAIZ)
    if raiz.handlers:
        return raiz
    raiz.setLevel(logging.DEBUG)
    raiz.propagate = False
    filtro = _Redige()
    fmt = _Formato("%(asctime)s [%(modulo)s] %(nivel)s%(message)s", "%Y-%m-%d %H:%M:%S")

    pasta = paths.pasta_logs()
    # delay: so abre o arquivo ao escrever; rotacao e segura porque as execucoes passam pela trava global
    principal = RotatingFileHandler(pasta / "sync.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8", delay=True)
    principal.setLevel(logging.INFO)
    detalhe = RotatingFileHandler(pasta / "debug.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8", delay=True)
    detalhe.setLevel(logging.DEBUG)
    handlers = [principal, detalhe]
    if console and sys.stderr is not None:  # pythonw nao tem console
        tela = logging.StreamHandler()
        tela.setLevel(logging.DEBUG if verbose else logging.INFO)
        handlers.append(tela)
    for h in handlers:
        h.addFilter(filtro)
        h.setFormatter(fmt)
        raiz.addHandler(h)
    principal.setFormatter(_SemTraceback(fmt._fmt, fmt.datefmt))
    for nome in ("googleapiclient", "google_auth_oauthlib", "google_auth_httplib2", "wsgiref", "urllib3"):
        logging.getLogger(nome).setLevel(logging.WARNING)
    return raiz


class _SemTraceback(_Formato):
    """No sync.log o traceback nao entra: so a linha; o detalhe fica no debug.log."""

    def formatException(self, ei):
        return ""

    def format(self, record):
        texto, record.exc_text = record.exc_text, None
        try:
            return super().format(record).rstrip()
        finally:
            record.exc_text = texto
