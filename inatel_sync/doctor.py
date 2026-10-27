"""inatel-sync doctor: confere cada peca e diz o que fazer quando algo falha."""

import sys

import requests

from inatel_sync import __version__
from inatel_sync.core import config as cfgmod
from inatel_sync.core import paths, segredos
from inatel_sync.core.erros import ErroInatelSync


def _linha(ok, texto, dica=""):
    marca = {True: "OK  ", False: "FALHA", None: "--  "}[ok]
    print(f"[{marca}] {texto}" + (f"\n         -> {dica}" if dica and ok is False else ""))
    return ok is not False


def diagnosticar():
    tudo = True
    print(f"inatel-sync {__version__} | Python {sys.version.split()[0]} | dados em {paths.pasta_dados()}")
    tudo &= _linha(sys.version_info >= (3, 12), f"Python {sys.version_info.major}.{sys.version_info.minor}",
                   "o inatel-sync precisa de Python 3.12+; reinstale pelo install.cmd")
    try:
        from inatel_sync.core.tempo import TZ  # noqa: F401
        tudo &= _linha(True, "fuso America/Sao_Paulo (tzdata)")
    except Exception:
        tudo &= _linha(False, "fuso America/Sao_Paulo", "pacote tzdata ausente; reinstale")

    try:
        cfg = cfgmod.carregar()
        tudo &= _linha(True, f"config valido ({paths.arquivo_config()})")
    except ErroInatelSync as e:
        _linha(False, "config", str(e))
        return 2

    from inatel_sync.core import google
    try:
        google.credenciais()
        google.servico_agenda().calendarList().list(maxResults=1).execute()
        extra = "" if google.tem_escopo("https://www.googleapis.com/auth/tasks") else " (sem Tasks)"
        tudo &= _linha(True, f"Google autorizado{extra}")
    except ErroInatelSync as e:
        tudo &= _linha(False, "Google", str(e))
    except Exception as e:
        tudo &= _linha(False, f"Google ({type(e).__name__})", "sem internet? tente de novo depois")

    p = cfg["portal"]
    if p["ativo"]:
        from inatel_sync.integracoes.portal import Portal, entrar
        senha = segredos.ler(segredos.PORTAL, Portal(cfg).usuario_senha())
        if not senha:
            tudo &= _linha(False, "senha do portal", "rode: inatel-sync config senha")
        else:
            try:
                entrar(p["login"], p["curso"], senha)
                tudo &= _linha(True, "login no Portal Academico")
            except ErroInatelSync as e:
                tudo &= _linha(False, "login no Portal Academico", str(e))
    else:
        _linha(None, "portal desligado")

    m = cfg["moodle"]
    from inatel_sync.integracoes.moodle import FONTES, baixar
    for fonte in m["fontes"] if m["ativo"] else []:
        try:
            baixar(fonte)
            tudo &= _linha(True, f"calendario de {FONTES[fonte][1]}")
        except ErroInatelSync as e:
            tudo &= _linha(False, FONTES[fonte][1], str(e))
    if not m["ativo"]:
        _linha(None, "Moodle desligado")

    if cfg["outlook"]["ativo"]:
        try:
            import win32com.client
            win32com.client.GetActiveObject("Outlook.Application")
            tudo &= _linha(True, "Outlook aberto")
        except Exception:
            _linha(None, "Outlook fechado agora (o sync abre escondido quando precisar)")

    from inatel_sync import integracoes
    from inatel_sync.core import agendador
    try:
        tarefas = agendador.listar()
        ativas = [n for n, i in integracoes.todas(cfg).items() if i.ativa]
        faltando = [n for n in ativas if n not in tarefas]
        tudo &= _linha(not faltando, f"tarefas agendadas ({', '.join(tarefas) or 'nenhuma'})",
                       f"faltam: {', '.join(faltando)}; rode: inatel-sync agendar")
        for nome, t in tarefas.items():
            if t.get("resultado") not in (0, 267009, 267011, None):  # 267009 rodando, 267011 nunca rodou
                _linha(False, f"tarefa {nome} terminou com codigo {t['resultado']}", "veja: inatel-sync status")
    except Exception as e:
        tudo &= _linha(False, f"Agendador do Windows ({type(e).__name__})")

    try:
        requests.get("https://www.google.com/generate_204", timeout=10)
        _linha(True, "internet")
    except requests.RequestException:
        tudo &= _linha(False, "internet", "sem conexao agora")
    print("\nTudo certo." if tudo else "\nHa itens com FALHA acima.")
    return 0 if tudo else 1
