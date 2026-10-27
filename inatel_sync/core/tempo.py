"""Fuso de Sao Paulo (zoneinfo: acompanha se o horario de verao voltar)."""

import datetime as dt
from zoneinfo import ZoneInfo

TZ_NAME = "America/Sao_Paulo"
TZ = ZoneInfo(TZ_NAME)  # no Windows precisa do pacote tzdata


def agora():
    return dt.datetime.now(TZ)


def hoje():
    return agora().date()


def inicio_do_dia(dia):
    return dt.datetime.combine(dia, dt.time(0, 0), TZ)
