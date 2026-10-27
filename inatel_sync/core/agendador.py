"""Tarefas do Agendador do Windows (nivel do usuario, sem admin), uma por integracao, na pasta \\inatel-sync.

Rodam sem janela (inatel-syncw.exe), "executar assim que possivel se perdeu o horario", uma instancia
por vez. No logon roda uma tarefa so (run all) com atraso, em vez de todas disparando juntas.
"""

import datetime as dt
import getpass
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

PASTA = "\\inatel-sync\\"
LOGON = "logon"
# Nomes da versao 1 (scripts soltos), removidos na migracao
LEGADO = ["Inatel - Sincronizar Agenda", "Inatel - Sincronizar Moodle", "Trabalho - Sincronizar Agenda",
          "GMUD - Marcar na Agenda"]
SEM_JANELA = 0x08000000  # CREATE_NO_WINDOW


def executavel():
    """(programa, prefixo de argumentos) para rodar sem console."""
    pasta = Path(sys.executable).parent
    for p in (pasta / "inatel-syncw.exe", pasta / "Scripts" / "inatel-syncw.exe"):
        if p.exists():
            return str(p), ""
    pythonw = pasta / "pythonw.exe"
    return str(pythonw if pythonw.exists() else sys.executable), "-m inatel_sync "


def _gatilhos(agenda):
    hoje = dt.date.today().isoformat()
    xs = []
    if "a_cada_min" in agenda:
        ini, fim = agenda["janela"]
        h1, m1 = map(int, ini.split(":"))
        h2, m2 = map(int, fim.split(":"))
        duracao = max((h2 * 60 + m2) - (h1 * 60 + m1), agenda["a_cada_min"])
        xs.append(f"""<CalendarTrigger><StartBoundary>{hoje}T{ini}:00</StartBoundary>
      <Repetition><Interval>PT{agenda['a_cada_min']}M</Interval><Duration>PT{duracao}M</Duration><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>""")
    for h in agenda.get("horarios", []):
        xs.append(f"<CalendarTrigger><StartBoundary>{hoje}T{h}:00</StartBoundary>"
                  "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>")
    if agenda.get("logon"):
        xs.append(f"<LogonTrigger><UserId>{escape(_usuario())}</UserId><Delay>PT2M</Delay></LogonTrigger>")
    return "\n    ".join(xs)


def _usuario():
    import os
    return f"{os.environ.get('USERDOMAIN', '')}\\{getpass.getuser()}".lstrip("\\")


def xml_tarefa(descricao, argumentos, agenda, limite_min=15):
    prog, prefixo = executavel()
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>{escape(descricao)}</Description></RegistrationInfo>
  <Triggers>
    {_gatilhos(agenda)}
  </Triggers>
  <Principals><Principal id="Author"><UserId>{escape(_usuario())}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <ExecutionTimeLimit>PT{limite_min}M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author"><Exec><Command>{escape(prog)}</Command><Arguments>{escape(prefixo + argumentos)}</Arguments></Exec></Actions>
</Task>"""


def _schtasks(*args):
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, creationflags=SEM_JANELA)


def criar(nome, descricao, argumentos, agenda):
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as f:
        f.write(xml_tarefa(descricao, argumentos, agenda))
    try:
        r = _schtasks("/create", "/tn", PASTA + nome, "/xml", f.name, "/f")
    finally:
        Path(f.name).unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError(f"schtasks recusou a tarefa {nome}: {(r.stderr or r.stdout).strip()}")


def remover(nome, pasta=PASTA):
    return _schtasks("/delete", "/tn", pasta + nome, "/f").returncode == 0


def listar():
    """{nome: {proxima, ultima, resultado, estado}} das tarefas na pasta \\inatel-sync."""
    ps = ("Get-ScheduledTask -TaskPath '\\inatel-sync\\' -ErrorAction SilentlyContinue | ForEach-Object { "
          "$i = $_ | Get-ScheduledTaskInfo; [pscustomobject]@{nome=$_.TaskName; estado=$_.State.ToString(); "
          "proxima=$(if ($i.NextRunTime) { $i.NextRunTime.ToString('s') }); "
          "ultima=$(if ($i.LastRunTime -and $i.LastRunTime.Year -gt 2000) { $i.LastRunTime.ToString('s') }); "
          "resultado=$i.LastTaskResult} } | ConvertTo-Json -Compress")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                       creationflags=SEM_JANELA, timeout=60)
    dados = json.loads(r.stdout or "[]") if r.stdout.strip() else []
    dados = [dados] if isinstance(dados, dict) else dados
    return {d["nome"]: d for d in dados}


def sincronizar_tarefas(integracoes, migrar_legado=False):
    """Cria/atualiza uma tarefa por integracao ativa, remove as de integracoes desligadas. Idempotente."""
    feitas, removidas = [], []
    existentes = listar()
    ativas = [i for i in integracoes if i.ativa]
    for i in ativas:
        criar(i.nome, f"inatel-sync: {i.titulo}", f"run {i.nome}", i.agendamento())
        feitas.append(i.nome)
    if ativas:
        criar(LOGON, "inatel-sync: sincroniza tudo ao entrar no Windows", "run all", {"logon": True})
        feitas.append(LOGON)
    for nome in existentes:
        if nome not in feitas and remover(nome):
            removidas.append(nome)
    if migrar_legado:
        removidas += [n for n in LEGADO if remover(n, "\\")]
    return feitas, removidas
