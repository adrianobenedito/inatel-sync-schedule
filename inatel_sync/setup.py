"""inatel-sync setup: assistente em portugues. Pode rodar de novo: mantem o que ja foi respondido."""

import getpass
import os
import shutil
from pathlib import Path

from inatel_sync.core import config as cfgmod
from inatel_sync.core import paths, segredos
from inatel_sync.core.config import CORES
from inatel_sync.core.erros import ErroInatelSync, ErroRede, PortalMudou

DOCS = Path(__file__).resolve().parent / "docs"
SKILL = Path(__file__).resolve().parent / "skill" / "inatel-sync"


# ---------------------------------------------------------------- perguntas

def _ler(prompt):
    return input(prompt).lstrip("﻿").strip()  # entrada redirecionada pode vir com BOM


def titulo(texto):
    print(f"\n=== {texto} " + "=" * max(0, 60 - len(texto)))


def sim_nao(pergunta, padrao=True):
    sufixo = "[S/n]" if padrao else "[s/N]"
    while True:
        r = _ler(f"{pergunta} {sufixo} ").lower()
        if not r:
            return padrao
        if r in ("s", "sim", "y", "yes"):
            return True
        if r in ("n", "nao", "não", "no"):
            return False
        print("  Responda s ou n.")


def texto(pergunta, padrao=""):
    r = _ler(f"{pergunta}" + (f" [{padrao}]" if padrao else "") + ": ")
    return r or padrao


def escolher(pergunta, opcoes, padrao=None):
    """opcoes: [(valor, rotulo)]. Devolve o valor."""
    for i, (_, rotulo) in enumerate(opcoes, 1):
        print(f"  {i:2}. {rotulo}")
    indice_padrao = next((i for i, (v, _) in enumerate(opcoes, 1) if v == padrao), None)
    while True:
        r = _ler(f"{pergunta}" + (f" [{indice_padrao}]" if indice_padrao else "") + ": ")
        if not r and indice_padrao:
            return opcoes[indice_padrao - 1][0]
        if r.isdigit() and 1 <= int(r) <= len(opcoes):
            return opcoes[int(r) - 1][0]
        print(f"  Digite um numero de 1 a {len(opcoes)}.")


def escolher_cor(pergunta, atual):
    return escolher(pergunta, [(n, n) for n in CORES], atual)


def horarios(pergunta, atuais):
    while True:
        r = texto(f"{pergunta} (HH:MM separados por virgula)", ", ".join(atuais))
        hs = [h.strip() for h in r.split(",") if h.strip()]
        if hs and all(cfgmod._HORA.match(h) for h in hs):
            return hs
        print("  Formato: 07:00, 13:00, 18:00")


# ---------------------------------------------------------------- portal

def _escolher_curso(atual):
    from inatel_sync.integracoes.portal import listar_cursos
    try:
        cursos = listar_cursos()
    except (ErroRede, PortalMudou) as e:
        print(f"  Nao consegui ler a lista de cursos do portal ({e}).")
        return texto("  Digite o codigo do curso", atual)
    print("Cursos do Portal Academico (Graduacao > Por Curso e Matricula):")
    return escolher("Qual e o seu curso", sorted(cursos, key=lambda c: c[1]), atual or None)


def _testar_login(login, curso, senha):
    """Tenta o login como digitado; se falhar e parecer a matricula completa, tenta a curta."""
    from inatel_sync.integracoes.portal import LoginRecusado, entrar
    tentativas = [login]
    if login.isdigit() and len(login) > 5:
        tentativas.append(str(int(login[-5:])))  # 14300123 -> 123
    for t in tentativas:
        try:
            entrar(t, curso, senha)
            return t
        except LoginRecusado:
            continue
    return None


def configurar_portal(cfg):
    p = cfg["portal"]
    titulo("Portal Inatel")
    provas = sim_nao("Colocar o CALENDARIO DE PROVAS na agenda?", p["provas"] if p["ativo"] else True)
    aulas = sim_nao("Colocar o QUADRO DE AULAS (aulas da semana) na agenda?", p["aulas"] if p["ativo"] else True)
    if not (provas or aulas):
        p["ativo"] = False
        return
    p.update(provas=provas, aulas=aulas)
    p["curso"] = _escolher_curso(p["curso"])
    print("\nO login do portal e a sua matricula. No Inatel costuma ser a matricula CURTA (sem o prefixo do curso e")
    print("do ano), por exemplo 123 em vez de 14300123. Se digitar a completa, eu testo as duas.")
    while True:
        login = texto("Matricula (login do portal)", p["login"])
        senha = getpass.getpass("Senha do portal (nao aparece enquanto digita): ")
        print("Testando o login no portal...")
        try:
            certo = _testar_login(login, p["curso"], senha)
        except ErroInatelSync as e:
            print(f"  Nao consegui testar agora: {e}")
            if sim_nao("  Guardar assim mesmo e testar depois?", False):
                certo = login
            else:
                continue
        if certo:
            break
        print("  O portal recusou. Confira o curso, a matricula e a senha.")
        if sim_nao("  Escolher o curso de novo?", False):
            p["curso"] = _escolher_curso(p["curso"])
    if certo != login:
        print(f"  Login aceito com a matricula curta: {certo}")
    p.update(ativo=True, login=certo, matricula=p["matricula"] if p["login"] == certo else "")
    segredos.gravar(segredos.PORTAL, str(p["matricula"] or certo), senha)
    print("  Senha guardada no Gerenciador de Credenciais do Windows (criptografada).")
    p["agenda"] = texto("Nome da agenda no Google para provas e aulas", p["agenda"])
    if provas:
        p["cor_provas"] = escolher_cor("Cor das provas", p["cor_provas"])
    if aulas:
        p["cor_aulas"] = escolher_cor("Cor das aulas", p["cor_aulas"])
        if sim_nao("Quer informar dias sem aula (recesso, semana de provas) ou a data do fim das aulas?", False):
            dias = texto("Dias sem aula (AAAA-MM-DD separados por virgula, Enter para nenhum)", ", ".join(p["sem_aula"]))
            p["sem_aula"] = [d.strip() for d in dias.split(",") if d.strip()]
            p["fim_aulas"] = texto("Ultimo dia de aula (AAAA-MM-DD; Enter = ate a ultima prova)", p["fim_aulas"])
    p["horarios"] = horarios("Horarios para sincronizar", p["horarios"])


# ---------------------------------------------------------------- moodle

def _colar_url(fonte):
    from inatel_sync.integracoes.moodle import FONTES, guardar_url, url_valida
    host = FONTES[fonte][1]
    print(f"""
Como pegar o link do calendario do {host}:
  1. Entre em https://{host} e abra o Calendario (menu lateral ou https://{host}/calendar/view.php).
  2. Clique em "Exportar calendario" (no fim da pagina) ou em "Importar ou exportar calendarios".
  3. Em "Eventos para exportar" marque "Todos os eventos"; em "Periodo", "Intervalo personalizado".
  4. Clique em "Obter URL do calendario" e depois em "Copiar URL".
O link tem um codigo pessoal: ele fica guardado criptografado no Windows, nunca em arquivo.""")
    while True:
        input("Copie o link e tecle Enter aqui (eu leio da area de transferencia)...")
        try:
            from inatel_sync.cli import _ler_area_transferencia
            url = _ler_area_transferencia()
        except Exception:
            url = ""
        if not url_valida(fonte, url):
            url = texto("Nao achei o link copiado. Cole aqui (botao direito) e tecle Enter").strip()
        if url_valida(fonte, url):
            guardar_url(fonte, url)
            return True
        print(f"  Isso nao parece o link de exportacao de {host}.")
        if not sim_nao("  Tentar de novo?"):
            return False


def configurar_moodle(cfg):
    from inatel_sync.integracoes.moodle import FONTES, baixar
    m = cfg["moodle"]
    titulo("Moodle")
    fontes = []
    for fonte, pergunta in (("moodle", "Colocar as entregas do MOODLE (moodle.inatel.br)?"),
                            ("code", "Colocar as entregas do MOODLE CODE (moodle-code.inatel.br)?")):
        if not sim_nao(pergunta, fonte in m["fontes"] if m["ativo"] else fonte == "moodle"):
            continue
        ja_tem = segredos.ler(segredos.MOODLE, FONTES[fonte][0])
        if ja_tem and sim_nao(f"  Ja tenho o link do {FONTES[fonte][1]}. Manter?"):
            fontes.append(fonte)
            continue
        if _colar_url(fonte):
            try:
                baixar(fonte)
                print(f"  Calendario do {FONTES[fonte][1]} lido com sucesso.")
            except ErroInatelSync as e:
                print(f"  Aviso: {e}")
            fontes.append(fonte)
    m.update(ativo=bool(fontes), fontes=fontes)
    if fontes:
        m["agenda"] = texto("Nome da agenda no Google para as entregas", m["agenda"] or cfg["portal"]["agenda"])
        m["cor"] = escolher_cor("Cor das entregas do Moodle", m["cor"])
        m["horarios"] = horarios("Horarios para sincronizar", m["horarios"])


# ---------------------------------------------------------------- outros

def _abrir(arquivo):
    try:
        os.startfile(arquivo)
    except OSError:
        print(f"  Abra este arquivo: {arquivo}")


def configurar_teams():
    titulo("Entregas do Teams")
    if sim_nao("Quer colocar as tarefas do Microsoft Teams na agenda? (e feito por um fluxo do Power Automate "
               "na sua conta Inatel; eu abro o passo a passo)", False):
        _abrir(DOCS / "teams-power-automate.md")
        input("Siga o guia no seu tempo. Tecle Enter para continuar o assistente...")


def _tem_outlook():
    try:
        import pywintypes
        pywintypes.IID("Outlook.Application")
        return True
    except Exception:
        return False


def configurar_outlook(cfg):
    o = cfg["outlook"]
    if not _tem_outlook():
        o["ativo"] = False
        return
    titulo("Outlook (agenda do trabalho)")
    if not sim_nao("Copiar as reunioes do Outlook deste computador para o Google Agenda? (so leitura no Outlook)",
                   o["ativo"]):
        o["ativo"] = False
        return
    o["ativo"] = True
    o["agenda"] = texto("Nome da agenda no Google para o trabalho", o["agenda"])
    o["cor"] = escolher_cor("Cor das reunioes", o["cor"])
    o["a_cada_min"] = int(texto("Sincronizar a cada quantos minutos", str(o["a_cada_min"])))
    ini = texto("Das (HH:MM)", o["janela"][0])
    fim = texto("Ate (HH:MM)", o["janela"][1])
    o["janela"] = [ini, fim]


def configurar_extras(cfg):
    c = cfg["cli"]
    titulo("Comandos extras")
    c["agenda"] = sim_nao("Usar o comando 'inatel-sync agenda' para marcar compromissos avulsos?", c["agenda"])
    c["tarefas"] = sim_nao("Usar o Google Tasks pelo comando 'inatel-sync tarefas'? (pede acesso ao Tasks)", c["tarefas"])


def instalar_skill():
    destino = Path.home() / ".claude" / "skills" / "inatel-sync"
    titulo("Claude")
    if not sim_nao("Voce usa o Claude (Claude Code)? Quer instalar a skill que ensina ele a operar o inatel-sync?",
                   destino.exists()):
        return
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SKILL / "SKILL.md", destino / "SKILL.md")
    print(f"  Skill instalada em {destino}")


def autorizar_google(cfg):
    from inatel_sync.core import google
    titulo("Google")
    if google.tem_token():
        try:
            google.credenciais()
            if not sim_nao("O Google ja esta autorizado. Autorizar de novo?", False):
                return
        except ErroInatelSync:
            print("A autorizacao do Google expirou; vamos renovar.")
    print("""Agora vou abrir o navegador para voce autorizar o acesso ao seu Google Agenda.
  - Use a sua conta Gmail PESSOAL (contas da faculdade ou empresa podem bloquear apps assim).
  - Vai aparecer "O Google nao verificou este app". E esperado: o inatel-sync e um projeto de aluno.
    Clique em "Avancado" e depois em "Acessar ... (nao seguro)".
  - Marque as permissoes pedidas (Agenda e, se escolheu, Tasks). Nada de e-mail, Drive ou contatos.""")
    input("Tecle Enter para abrir o navegador...")
    google.autorizar(incluir_tarefas=cfg["cli"]["tarefas"])
    print("  Google autorizado.")


def testar_agendas(cfg):
    from inatel_sync.core import google
    service = google.servico_agenda()
    nomes = {cfg[s]["agenda"] for s in ("portal", "moodle", "outlook") if cfg[s]["ativo"]}
    for nome in sorted(nomes):
        google.id_da_agenda(service, nome)
        print(f"  Agenda pronta no Google: {nome}")


def primeira_sincronizacao(cfg):
    from inatel_sync import integracoes
    from inatel_sync.core.executor import rodar
    from inatel_sync.integracoes.base import Contexto
    ativas = [i for i in integracoes.todas(cfg).values() if i.ativa]
    if not ativas:
        return
    titulo("Primeira sincronizacao")
    print("Simulacao (nada e alterado ainda). Linhas com + entram na agenda, ~ mudam, - saem:\n")
    rodar(ativas, Contexto(cfg, dry_run=True))
    if sim_nao("\nAplicar isso na sua agenda agora?"):
        rodar(ativas, Contexto(cfg))


def criar_tarefas(cfg):
    from inatel_sync import integracoes
    from inatel_sync.core import agendador
    titulo("Agendador do Windows")
    try:
        feitas, removidas = agendador.sincronizar_tarefas(integracoes.todas(cfg).values())
        print(f"  Tarefas prontas (rodam sozinhas, sem janela): {', '.join(feitas) or 'nenhuma'}")
        if removidas:
            print(f"  Removidas (integracoes desligadas): {', '.join(removidas)}")
    except Exception as e:
        print(f"  Nao consegui criar as tarefas ({e}). Tente depois: inatel-sync agendar")


def assistente():
    novo = not paths.arquivo_config().exists()
    cfg = cfgmod.carregar(exigir=False) if novo else cfgmod.carregar()
    print("inatel-sync: vou perguntar o que voce quer na sua agenda. Enter aceita a opcao entre [colchetes].")
    if not novo:
        print("Voce ja tem uma configuracao: as respostas anteriores aparecem como padrao.")
    configurar_portal(cfg)
    configurar_moodle(cfg)
    configurar_teams()
    configurar_outlook(cfg)
    configurar_extras(cfg)
    cfgmod.salvar(cfg)
    print(f"\nConfiguracao salva em {paths.arquivo_config()}")
    instalar_skill()
    if not any(cfg[s]["ativo"] for s in ("portal", "moodle", "outlook")) and not any(cfg["cli"].values()):
        print("Nada foi escolhido. Rode 'inatel-sync setup' quando quiser ligar alguma parte.")
        return 0
    autorizar_google(cfg)
    testar_agendas(cfg)
    criar_tarefas(cfg)
    primeira_sincronizacao(cfg)
    titulo("Pronto")
    print("""A sua agenda vai se atualizar sozinha. Comandos uteis (no Prompt de Comando ou PowerShell):
  inatel-sync status      o que rodou e quando roda de novo
  inatel-sync run         sincroniza agora
  inatel-sync doctor      diagnostico se algo parecer errado
  inatel-sync setup       muda as respostas (este assistente)""")
    return 0
