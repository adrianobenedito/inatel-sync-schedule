"""Outlook desktop (calendario padrao deste PC) -> agenda do trabalho. So leitura no Outlook.

Se o Outlook estiver fechado, o COM abre ele escondido; se nao responder em `espera_s`
(perfil pedindo senha, por exemplo), pula com aviso em vez de deixar a tarefa pendurada.
"""

import datetime as dt
import locale
import queue
import threading

from inatel_sync.core.engine import Evento
from inatel_sync.core.erros import Aviso
from inatel_sync.core.feriados import eh_feriado
from inatel_sync.core.tempo import TZ, hoje, inicio_do_dia
from inatel_sync.integracoes.base import Coleta, Integracao

MAX_DESCRICAO = 7000
CANCELADA = {5, 7}  # olMeetingCanceled, olMeetingReceivedAndCanceled
OL_FOLDER_CALENDAR = 9
OL_APPOINTMENT = 26


def _outlook_aberto():
    import win32com.client

    try:
        win32com.client.GetActiveObject("Outlook.Application")
        return True
    except Exception:
        return False


def _data_filtro(t):
    # O Restrict entende a data no formato regional do Windows (dd/mm em pt-BR, mm/dd em en-US).
    locale.setlocale(locale.LC_TIME, "")
    return t.strftime("%x %H:%M")


def _ler(primeiro, ultimo, cor):
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        ns = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        itens = ns.GetDefaultFolder(OL_FOLDER_CALENDAR).Items
        itens.Sort("[Start]")  # a Microsoft pede Sort antes de IncludeRecurrences
        itens.IncludeRecurrences = True
        filtrados = itens.Restrict(f"[End] > '{_data_filtro(primeiro)}' AND [Start] < '{_data_filtro(ultimo)}'")
        result = []
        it = filtrados.GetFirst()
        while it is not None:
            if getattr(it, "Class", None) == OL_APPOINTMENT and it.MeetingStatus not in CANCELADA:
                e = _evento(it, cor)
                if e:
                    result.append(e)
            it = filtrados.GetNext()
        return result
    finally:
        pythoncom.CoUninitialize()


def _evento(it, cor):
    # StartUTC/EndUTC vem em UTC (o pywin32 ja marca como UTC).
    inicio, fim = it.StartUTC.astimezone(TZ), it.EndUTC.astimezone(TZ)
    # Recorrencia do Outlook nao pula feriado; reuniao avulsa num feriado continua.
    if it.IsRecurring and eh_feriado(inicio.date()):
        return None
    descricao = (it.Body or "").strip()
    if len(descricao) > MAX_DESCRICAO:
        descricao = descricao[:MAX_DESCRICAO] + "\n[...]"
    e = Evento(
        chave=f"outlook|{it.GlobalAppointmentID}|{inicio.isoformat()}",
        titulo=it.Subject or "(sem titulo)", dia=inicio.date(), inicio=inicio, fim=fim,
        local=it.Location or "", descricao=descricao,
        lembretes=[it.ReminderMinutesBeforeStart] if it.ReminderSet else [], cor=cor,
    )
    if it.AllDayEvent:
        # Start/End de dia inteiro sao datas locais; End e o dia seguinte ao ultimo
        dia, depois = it.Start.date(), it.End.date()
        e.inicio = e.fim = None
        e.dia = dia
        if depois - dia > dt.timedelta(days=1):
            e.ultimo_dia = depois - dt.timedelta(days=1)
    return e


class Outlook(Integracao):
    nome = "outlook"
    titulo = "Outlook (agenda do trabalho)"
    prefixos = ("outlook|",)

    def coletar(self):
        if not self.opcoes.get("abrir_se_fechado", True) and not _outlook_aberto():
            raise Aviso("o Outlook esta fechado (abrir_se_fechado = false)")
        desde = inicio_do_dia(hoje())
        ate = desde + dt.timedelta(days=self.opcoes.get("dias", 60))
        resposta = queue.Queue()

        def trabalho():
            try:
                resposta.put(("ok", _ler(desde.replace(tzinfo=None), ate.replace(tzinfo=None), self.cor())))
            except Exception as e:
                resposta.put(("erro", e))

        # daemon: se o Outlook travar, o processo termina mesmo assim
        threading.Thread(target=trabalho, daemon=True).start()
        try:
            tipo, valor = resposta.get(timeout=self.opcoes.get("espera_s", 60))
        except queue.Empty:
            raise Aviso(f"o Outlook nao respondeu em {self.opcoes.get('espera_s', 60)} s") from None
        if tipo == "erro":
            raise Aviso(f"nao consegui ler o Outlook ({type(valor).__name__}: {valor})") from valor
        self.log.info("Outlook: %d compromissos nos proximos %d dias", len(valor), self.opcoes.get("dias", 60))
        # Lista vazia (perfil nao carregou): nao apaga o que ja existe.
        return Coleta(valor, self.prefixos if valor else (), desde=desde, ate=ate)
