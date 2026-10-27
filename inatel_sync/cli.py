"""inatel-sync: ponto de entrada unico.

  inatel-sync run [modulo ...|all] [--dry-run] [--forcar]   sincroniza (padrao: todos os ativos)
  inatel-sync status                                       ultima execucao e proxima de cada modulo
  inatel-sync doctor                                       diagnostico (rede, portal, Google, tarefas)
  inatel-sync auth                                         autoriza (ou reautoriza) o Google
  inatel-sync config ...                                   mostrar, senha, moodle-url, set, integracao, importar
  inatel-sync agenda add|remove ...                        compromisso avulso no Google Agenda
  inatel-sync tarefas add|list|done|remove ...             Google Tasks
  inatel-sync agendar                                      cria/atualiza as tarefas do Agendador do Windows
"""

import argparse
import sys

from inatel_sync import __version__
from inatel_sync.core import config as cfgmod
from inatel_sync.core import log
from inatel_sync.core.erros import AcaoNecessaria, ErroConfig

_log = log.logger("cli")


def _cfg():
    return cfgmod.carregar()


# ---------------------------------------------------------------- run / status

def cmd_run(args):
    from inatel_sync import integracoes
    from inatel_sync.core.executor import rodar
    from inatel_sync.integracoes.base import Contexto

    cfg = _cfg()
    todas = integracoes.todas(cfg)
    nomes = args.modulos or ["all"]
    if "all" in nomes:
        escolhidas = [i for i in todas.values() if i.ativa]
    else:
        desconhecidos = [n for n in nomes if n not in todas]
        if desconhecidos:
            raise ErroConfig(f"modulo desconhecido: {', '.join(desconhecidos)} (opcoes: {', '.join(todas)}, all)")
        escolhidas = [todas[n] for n in nomes]
        for i in escolhidas:
            if not i.ativa:
                _log.warning("%s esta desligado no config; rodando mesmo assim porque foi pedido", i.nome)
    if not escolhidas:
        _log.warning("Nenhuma integracao ativa. Rode: inatel-sync setup")
        return 0
    return rodar(escolhidas, Contexto(cfg, dry_run=args.dry_run, forcar=args.forcar))


def cmd_status(args):
    from inatel_sync import integracoes
    from inatel_sync.core import agendador, estado

    cfg = _cfg()
    execs = estado.carregar().get("execucoes", {})
    try:
        tarefas = agendador.listar()
    except Exception:
        tarefas = {}
    print(f"inatel-sync {__version__}")
    for nome, integ in integracoes.todas(cfg).items():
        e = execs.get(nome, {})
        t = tarefas.get(nome, {})
        situacao = "ativo" if integ.ativa else "desligado"
        print(f"\n{integ.titulo} [{nome}] - {situacao}")
        if e:
            print(f"  ultima execucao: {e['inicio'][:16].replace('T', ' ')} -> {e['resultado']}: {e['mensagem']}")
            if e["resultado"] != "ok" and e.get("ultimo_ok"):
                print(f"  ultimo sucesso:  {e['ultimo_ok'][:16].replace('T', ' ')}")
        elif integ.ativa:
            print("  ainda nao rodou")
        if integ.ativa:
            print(f"  proxima:         {t['proxima'][:16].replace('T', ' ') if t.get('proxima') else 'sem tarefa agendada (rode: inatel-sync agendar)'}")
    if logon := tarefas.get("logon"):
        print(f"\nAo entrar no Windows: run all (tarefa {logon['estado']})")
    return 0


# ---------------------------------------------------------------- auth / config

def _cfg_opcional():
    from inatel_sync.core import config
    return config.carregar(exigir=False)


def cmd_setup(args):
    from inatel_sync import setup
    return setup.assistente()


def cmd_desinstalar(args):
    from inatel_sync import desinstalar
    return desinstalar.desinstalar(manter_dados=args.manter_dados, sim=args.sim)


def cmd_auth(args):
    from inatel_sync.core import google

    print("Vai abrir o navegador para voce autorizar o acesso ao Google Agenda e ao Google Tasks.")
    print('Se aparecer "O Google nao verificou este app": clique em "Avancado" e depois em "Acessar ... (nao seguro)".')
    print("O inatel-sync pede so Agenda e Tasks; nada de e-mail, Drive ou contatos.")
    cfg = _cfg_opcional()
    google.autorizar(incluir_tarefas=cfg["cli"]["tarefas"])
    google.servico_agenda().calendarList().list(maxResults=1).execute()
    print("Google autorizado.")
    return 0


def _ler_area_transferencia():
    import win32clipboard

    win32clipboard.OpenClipboard()
    try:
        return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT).strip()
    finally:
        win32clipboard.CloseClipboard()


def cmd_config(args):
    from inatel_sync.core import segredos

    if args.acao == "importar":
        from inatel_sync.migracao import importar_v1
        return importar_v1(args.valor[0] if args.valor else ".")
    cfg = _cfg()
    if args.acao == "mostrar":
        import tomli_w
        print(tomli_w.dumps(cfg))
        return 0
    if args.acao == "senha":
        import getpass
        from inatel_sync.integracoes.portal import Portal, entrar, LoginRecusado
        p = Portal(cfg)
        senha = getpass.getpass(f"Senha do Portal Academico (login {cfg['portal']['login']}): ")
        try:
            entrar(cfg["portal"]["login"], cfg["portal"]["curso"], senha)
        except LoginRecusado:
            print("O portal recusou essa senha; nada foi alterado.")
            return 2
        segredos.gravar(segredos.PORTAL, p.usuario_senha(), senha)
        print("Senha testada no portal e guardada no Gerenciador de Credenciais do Windows.")
        return 0
    if args.acao == "moodle-url":
        from inatel_sync.integracoes.moodle import FONTES, guardar_url
        fonte = (args.valor or ["moodle"])[0]
        if fonte not in FONTES:
            raise ErroConfig(f"fonte {fonte!r}: use moodle ou code")
        print(f"Copie o URL do calendario de {FONTES[fonte][1]} (Exportar calendario > Obter URL > Copiar URL).")
        url = _ler_area_transferencia()
        if not url.startswith("http"):
            url = input("Cole o URL aqui e tecle Enter: ").strip()
        guardar_url(fonte, url)
        if fonte not in cfg["moodle"]["fontes"]:
            cfg["moodle"]["fontes"].append(fonte)
            cfgmod.salvar(cfg)
        print(f"Link de {FONTES[fonte][1]} guardado no Gerenciador de Credenciais do Windows.")
        return 0
    if args.acao == "set":
        if len(args.valor or []) != 2:
            raise ErroConfig("uso: inatel-sync config set secao.chave valor")
        v = cfgmod.definir(cfg, *args.valor)
        cfgmod.salvar(cfg)
        print(f"{args.valor[0]} = {v!r}")
        return 0
    if args.acao == "integracao":
        if len(args.valor or []) != 2 or args.valor[1] not in ("on", "off"):
            raise ErroConfig("uso: inatel-sync config integracao <nome> on|off")
        nome, liga = args.valor[0], args.valor[1] == "on"
        if nome not in cfg or not isinstance(cfg[nome], dict):
            raise ErroConfig(f"integracao desconhecida: {nome}")
        cfg[nome]["ativo"] = liga
        cfgmod.salvar(cfg)
        print(f"{nome}: {'ligado' if liga else 'desligado'}. Para atualizar as tarefas do Agendador: inatel-sync agendar")
        return 0
    return 0


def cmd_agendar(args):
    from inatel_sync import integracoes
    from inatel_sync.core import agendador

    feitas, removidas = agendador.sincronizar_tarefas(integracoes.todas(_cfg()).values(), args.migrar_legado)
    print("Tarefas criadas/atualizadas:", ", ".join(feitas) or "nenhuma")
    if removidas:
        print("Tarefas removidas:", ", ".join(removidas))
    return 0


# ---------------------------------------------------------------- agenda / tarefas

def cmd_agenda(args):
    from inatel_sync import agenda
    from inatel_sync.core.executor import rodar_protegido

    cfg = _cfg()
    lg = log.logger("agenda")

    def fazer():
        if args.cmd2 == "add":
            if not args.data and not args.inicio:
                raise ErroConfig("Informe --data (dia inteiro) ou --inicio.")
            acao, ev = agenda.adicionar(cfg, args.titulo, args.data, args.inicio, args.fim, args.descricao, args.local,
                                        args.agenda, args.chave, args.lembrete, args.cor, args.ate, args.repetir,
                                        dry_run=args.dry_run)
            lg.info("%s: %s (%s)", acao, args.titulo, args.inicio or args.data)
        else:
            n = agenda.remover(cfg, args.chave, args.agenda, dry_run=args.dry_run)
            lg.info("%s: %d (chave %s)", "removeria" if args.dry_run else "removidos", n, args.chave)
    return rodar_protegido(fazer, "agenda")


def cmd_tarefas(args):
    from inatel_sync import tarefas
    from inatel_sync.core.executor import rodar_protegido

    lg = log.logger("tarefas")

    def fazer():
        if args.cmd2 == "add":
            acao, _ = tarefas.adicionar(args.titulo, args.data, args.notas, args.lista, args.chave)
            lg.info("%s: %s%s", acao, args.titulo, f" (prazo {args.data})" if args.data else "")
        elif args.cmd2 == "list":
            for lista, titulo, prazo, notas in tarefas.pendentes(args.lista):
                print(f"{prazo or 'sem prazo':10}  [{lista}] {titulo}" + (f"  -- {notas.strip()}" if notas.strip() else ""))
        elif args.cmd2 == "done":
            if not args.chave and not args.titulo:
                raise ErroConfig("Informe --chave ou --titulo.")
            lg.info("concluidas: %d", tarefas.concluir(args.chave, args.titulo, args.lista))
        else:
            lg.info("removidas: %d (chave %s)", tarefas.remover(args.chave, args.lista), args.chave)
    return rodar_protegido(fazer, "tarefas")


def cmd_doctor(args):
    from inatel_sync.doctor import diagnosticar
    return diagnosticar()


# ---------------------------------------------------------------- argparse

def _parser():
    from inatel_sync.agenda import REPETIR
    from inatel_sync.core.config import CORES

    ap = argparse.ArgumentParser(prog="inatel-sync", description="Mantem o Google Agenda atualizado.")
    ap.add_argument("--version", action="version", version=f"inatel-sync {__version__}")
    ap.add_argument("-v", "--verbose", action="store_true", help="mostra detalhes (debug)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="sincroniza agora")
    r.add_argument("modulos", nargs="*", help="portal, moodle, outlook ... ou all (padrao)")
    r.add_argument("--dry-run", action="store_true", help="mostra o que mudaria, sem alterar a agenda")
    r.add_argument("--forcar", action="store_true", help="passa pela trava contra apagar muitos eventos")
    r.set_defaults(func=cmd_run)

    sub.add_parser("status", help="ultima e proxima execucao de cada modulo").set_defaults(func=cmd_status)
    sub.add_parser("doctor", help="diagnostico").set_defaults(func=cmd_doctor)
    sub.add_parser("auth", help="autoriza o Google (abre o navegador)").set_defaults(func=cmd_auth)
    sub.add_parser("setup", help="assistente de configuracao (pode rodar de novo)").set_defaults(func=cmd_setup)
    d = sub.add_parser("desinstalar", help="remove tarefas, senhas guardadas e (opcional) os dados")
    d.add_argument("--manter-dados", action="store_true", help="mantem config e estado para reinstalar depois")
    d.add_argument("--sim", action="store_true", help="nao pergunta")
    d.set_defaults(func=cmd_desinstalar)

    c = sub.add_parser("config", help="mostrar | senha | moodle-url [moodle|code] | set secao.chave valor | "
                                      "integracao <nome> on|off | importar <pasta da versao 1>")
    c.add_argument("acao", choices=["mostrar", "senha", "moodle-url", "set", "integracao", "importar"])
    c.add_argument("valor", nargs="*")
    c.set_defaults(func=cmd_config)

    g = sub.add_parser("agendar", help="cria/atualiza as tarefas do Agendador do Windows")
    g.add_argument("--migrar-legado", action="store_true", help="remove as tarefas da versao 1")
    g.set_defaults(func=cmd_agendar)

    a = sub.add_parser("agenda", help="compromisso avulso no Google Agenda")
    asub = a.add_subparsers(dest="cmd2", required=True)
    aa = asub.add_parser("add", help="cria ou atualiza um compromisso")
    aa.add_argument("--titulo", required=True)
    aa.add_argument("--data", help="AAAA-MM-DD (dia inteiro)")
    aa.add_argument("--ate", help="AAAA-MM-DD, ultimo dia de um evento de dia inteiro com varios dias")
    aa.add_argument("--inicio", help="'AAAA-MM-DD HH:MM'")
    aa.add_argument("--fim", help="'AAAA-MM-DD HH:MM' (padrao: 1h depois do inicio)")
    aa.add_argument("--descricao", default="")
    aa.add_argument("--local", default="")
    aa.add_argument("--agenda", default="principal", help="principal, Trabalho, Inatel ou outro nome (cria se nao existir)")
    aa.add_argument("--chave", help="identificador para atualizar depois sem duplicar")
    aa.add_argument("--lembrete", type=int, action="append", default=[], help="minutos antes (pode repetir)")
    aa.add_argument("--cor", help=", ".join(CORES))
    aa.add_argument("--repetir", choices=list(REPETIR), help="repete a partir de --data/--inicio")
    aa.add_argument("--dry-run", action="store_true")
    ar = asub.add_parser("remove", help="remove o compromisso com essa chave")
    ar.add_argument("--chave", required=True)
    ar.add_argument("--agenda", default="principal")
    ar.add_argument("--dry-run", action="store_true")
    a.set_defaults(func=cmd_agenda)

    t = sub.add_parser("tarefas", help="Google Tasks")
    tsub = t.add_subparsers(dest="cmd2", required=True)
    ta = tsub.add_parser("add", help="cria ou atualiza uma tarefa")
    ta.add_argument("--titulo", required=True)
    ta.add_argument("--data", help="AAAA-MM-DD (prazo, opcional)")
    ta.add_argument("--notas", default="")
    ta.add_argument("--lista", default="principal", help="principal ou o nome de uma lista (cria se nao existir)")
    ta.add_argument("--chave", help="identificador para atualizar/concluir depois sem duplicar")
    tl = tsub.add_parser("list", help="mostra as tarefas abertas")
    tl.add_argument("--lista", help="so esta lista (padrao: todas)")
    td = tsub.add_parser("done", help="marca como concluida")
    td.add_argument("--chave")
    td.add_argument("--titulo", help="titulo exato, se a tarefa nao tiver chave")
    td.add_argument("--lista", default="principal")
    tr = tsub.add_parser("remove", help="apaga a tarefa com essa chave")
    tr.add_argument("--chave", required=True)
    tr.add_argument("--lista", default="principal")
    t.set_defaults(func=cmd_tarefas)
    return ap


def main(argv=None):
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    log.configurar(verbose=args.verbose)
    try:
        codigo = args.func(args)
    except AcaoNecessaria as e:
        _log.error("%s", e)
        codigo = 2
    except KeyboardInterrupt:
        codigo = 130
    except Exception as e:
        from inatel_sync.core.erros import eh_erro_rede, resumo_rede
        if eh_erro_rede(e):
            _log.warning("sem conexao (%s); tente de novo depois", resumo_rede(e))
            codigo = 3
        else:
            _log.error("erro inesperado: %s: %s (detalhes em debug.log)", type(e).__name__, e, exc_info=True)
            codigo = 1
    sys.exit(codigo or 0)
