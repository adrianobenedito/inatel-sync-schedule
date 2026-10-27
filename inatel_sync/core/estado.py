"""estado.json: ids das agendas e resultado da ultima execucao de cada modulo."""

import datetime as dt
import json

from inatel_sync.core import paths
from inatel_sync.core.trava import gravar_atomico


def carregar():
    arq = paths.arquivo_estado()
    if not arq.exists():
        return {}
    try:
        return json.loads(arq.read_text(encoding="utf-8-sig"))
    except ValueError:
        arq.replace(arq.with_name("estado.corrompido.json"))  # guarda para analise e recomeca
        return {}


def atualizar(funcao):
    """Le, aplica funcao(estado) e grava atomicamente."""
    est = carregar()
    funcao(est)
    gravar_atomico(paths.arquivo_estado(), json.dumps(est, indent=2, ensure_ascii=False))
    return est


def registrar_execucao(modulo, resultado, mensagem, inicio, duracao):
    def f(est):
        execucoes = est.setdefault("execucoes", {})
        ultimo_ok = execucoes.get(modulo, {}).get("ultimo_ok")
        if resultado == "ok":
            ultimo_ok = inicio.isoformat(timespec="seconds")
        execucoes[modulo] = {
            "inicio": inicio.isoformat(timespec="seconds"),
            "duracao_s": round(duracao, 1),
            "resultado": resultado,  # ok, aviso, acao, erro
            "mensagem": mensagem,
            "ultimo_ok": ultimo_ok,
        }
    atualizar(f)


def agora():
    return dt.datetime.now().astimezone()
