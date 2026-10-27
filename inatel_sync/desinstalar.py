"""Desinstalacao: tarefas, senhas do keyring, skill e (opcional) dados. Os eventos da agenda ficam.

A pasta do programa (%LOCALAPPDATA%\\inatel-sync) e o PATH sao removidos pelo uninstall.cmd,
porque o Python que roda isto esta dentro dela.
"""

import logging
import shutil
from pathlib import Path

from inatel_sync.core import agendador, paths, segredos


def _usuarios_portal():
    from inatel_sync.core import config
    try:
        p = config.carregar(exigir=False)["portal"]
    except Exception:
        return []
    return [u for u in {str(p.get("matricula") or ""), str(p.get("login") or "")} if u]


def desinstalar(manter_dados=False, sim=False):
    if not sim:
        print("Isto remove as tarefas agendadas, as senhas guardadas e a autorizacao do Google.")
        print("Os eventos que ja estao no seu Google Agenda NAO sao apagados.")
        if input("Continuar? [s/N] ").strip().lower() not in ("s", "sim"):
            print("Nada foi removido.")
            return 0
    for nome in agendador.listar():
        agendador.remover(nome)
    agendador.remover_pasta()
    for usuario in _usuarios_portal():
        segredos.apagar(segredos.PORTAL, usuario)
    segredos.apagar(segredos.MOODLE, "ical")
    segredos.apagar(segredos.MOODLE, "ical-code")
    segredos.apagar(segredos.GOOGLE, "token")
    skill = Path.home() / ".claude" / "skills" / "inatel-sync"
    if skill.exists():
        shutil.rmtree(skill, ignore_errors=True)
    if not manter_dados:
        logging.shutdown()  # solta os arquivos de log antes de apagar a pasta
        shutil.rmtree(paths.pasta_dados(), ignore_errors=True)
    print("inatel-sync removido." + (f" Configuracao mantida em {paths.pasta_dados()}" if manter_dados else ""))
    print("Para tirar tambem o acesso do Google: https://myaccount.google.com/permissions")
    return 0
