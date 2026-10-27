"""Interface comum: cada integracao coleta eventos de uma fonte; a engine cuida do Google."""

from dataclasses import dataclass

from googleapiclient.errors import HttpError

from inatel_sync.core import google, log
from inatel_sync.core.config import cor_id
from inatel_sync.core.engine import AgendaGoogle, sincronizar
from inatel_sync.core.tempo import hoje, inicio_do_dia


@dataclass
class Coleta:
    eventos: list
    prefixos: tuple  # so estes prefixos vieram confiaveis; os outros nao sao apagados nesta execucao
    desde: object = None  # padrao: hoje 00:00
    ate: object = None  # padrao: sem limite


@dataclass
class Contexto:
    cfg: dict
    dry_run: bool = False
    forcar: bool = False
    api: object = None  # AgendaGoogle (ou falso nos testes)


class Integracao:
    nome = ""  # nome no config e na linha de comando
    titulo = ""
    prefixos = ()  # chaves que esta integracao cria e as unicas que ela pode apagar
    requer_google = True

    def __init__(self, cfg):
        self.cfg = cfg
        self.opcoes = cfg.get(self.nome, {})
        self.log = log.logger(self.nome)

    @property
    def ativa(self):
        return bool(self.opcoes.get("ativo"))

    def agendamento(self):
        """{"horarios": ["07:00", ...]} ou {"a_cada_min": 30, "janela": ["07:00", "22:00"]}."""
        if self.opcoes.get("a_cada_min"):
            return {"a_cada_min": self.opcoes["a_cada_min"], "janela": self.opcoes.get("janela", ["07:00", "22:00"])}
        return {"horarios": self.opcoes.get("horarios", [])}

    def cor(self, chave="cor"):
        return cor_id(self.opcoes.get(chave)) if self.opcoes.get(chave) else None

    def coletar(self):
        raise NotImplementedError

    def executar(self, ctx):
        coleta = self.coletar()
        service = google.servico_agenda()
        api = ctx.api or AgendaGoogle(service)
        nome_agenda = self.opcoes["agenda"]
        args = dict(ate=coleta.ate, dry_run=ctx.dry_run, forcar=ctx.forcar, nome=self.nome, log=self.log,
                    limite=(ctx.cfg["trava"]["max_apagar"], ctx.cfg["trava"]["max_apagar_pct"]))
        desde = coleta.desde or inicio_do_dia(hoje())
        cal_id = google.id_da_agenda(service, nome_agenda)
        try:
            return sincronizar(api, cal_id, coleta.eventos, coleta.prefixos, desde, **args)
        except HttpError as e:
            if e.resp.status not in (404, 410):
                raise
            # id guardado de uma agenda apagada: procura pelo nome (ou cria) e tenta uma vez mais
            cal_id = google.id_da_agenda(service, nome_agenda, conferir=True)
            return sincronizar(api, cal_id, coleta.eventos, coleta.prefixos, desde, **args)
