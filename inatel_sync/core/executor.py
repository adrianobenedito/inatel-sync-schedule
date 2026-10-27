"""Roda as integracoes pedidas, uma de cada vez, dentro da trava global.

Falha esperada (rede, VPN, portal fora) vira uma linha de aviso e nada e apagado.
Codigos de saida: 0 ok/aviso, 2 precisa de acao da pessoa, 1 erro inesperado.
"""

import time

from inatel_sync.core import estado, log
from inatel_sync.core.erros import AcaoNecessaria, Aviso, eh_erro_rede, resumo_rede
from inatel_sync.core.trava import trava


def _rodar_uma(integ, ctx):
    lg = integ.log
    inicio, t0 = estado.agora(), time.perf_counter()
    codigo = 0
    try:
        resumo = integ.executar(ctx)
        resultado, msg = "ok", resumo.texto(ctx.dry_run) if resumo else "ok"
        if resumo and (resumo.retidos or resumo.falhas):
            resultado = "aviso"
    except Aviso as e:
        resultado, msg = "aviso", str(e)
        lg.warning("%s; nada foi alterado", msg)
    except AcaoNecessaria as e:
        resultado, msg, codigo = "acao", str(e), 2
        lg.error("%s", msg)
    except Exception as e:
        if eh_erro_rede(e):
            resultado, msg = "aviso", f"sem conexao ({resumo_rede(e)})"
            lg.warning("%s; nada foi alterado", msg)
            lg.debug("detalhe do erro de rede", exc_info=True)
        else:
            resultado, msg, codigo = "erro", f"erro inesperado: {type(e).__name__}: {e}", 1
            lg.error("%s (detalhes em debug.log)", msg, exc_info=True)
    duracao = time.perf_counter() - t0
    lg.debug("duracao %.1fs", duracao)
    if not ctx.dry_run:
        estado.registrar_execucao(integ.nome, resultado, msg, inicio, duracao)
    return codigo


def rodar(integracoes, ctx):
    with trava():
        codigos = [_rodar_uma(i, ctx) for i in integracoes]
    return 1 if 1 in codigos else max(codigos, default=0)


def rodar_protegido(funcao, modulo):
    """Para comandos avulsos (agenda, tarefas): mesma classificacao de erros, sem registrar execucao."""
    lg = log.logger(modulo)
    try:
        with trava(espera=60):
            return funcao() or 0
    except Aviso as e:
        lg.warning("%s", e)
        return 3
    except AcaoNecessaria as e:
        lg.error("%s", e)
        return 2
    except Exception as e:
        if eh_erro_rede(e):
            lg.warning("sem conexao (%s)", resumo_rede(e))
            return 3
        lg.error("erro inesperado: %s: %s (detalhes em debug.log)", type(e).__name__, e, exc_info=True)
        return 1
