"""Feriados nacionais (fixos + Sexta-feira Santa)."""

import datetime as dt
import functools

FIXOS = ["01-01", "04-21", "05-01", "09-07", "10-12", "11-02", "11-15", "11-20", "12-25"]


def pascoa(ano):
    # algoritmo de Meeus/Jones/Butcher
    a, b, c = ano % 19, ano // 100, ano % 100
    g = (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - b // 4 - g + 15) % 30
    l = (32 + 2 * (b % 4) + 2 * (c // 4) - h - c % 4) % 7
    m = (a + 11 * h + 22 * l) // 451
    return dt.date(ano, (h + l - 7 * m + 114) // 31, (h + l - 7 * m + 114) % 31 + 1)


@functools.cache
def nacionais(ano):
    return frozenset({dt.date.fromisoformat(f"{ano}-{d}") for d in FIXOS} | {pascoa(ano) - dt.timedelta(days=2)})


def eh_feriado(dia):
    return dia in nacionais(dia.year)
