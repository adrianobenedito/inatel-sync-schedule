import datetime as dt

from conftest import AGORA, AgendaFalsa, dia

from inatel_sync.core.engine import Evento, comparavel, sincronizar
from inatel_sync.core.tempo import TZ, inicio_do_dia


def evento(chave, n=1, titulo=None, hora=19):
    ini = dt.datetime.combine(dia(n), dt.time(hora), TZ)
    return Evento(chave=chave, titulo=titulo or chave, dia=dia(n), inicio=ini, fim=ini + dt.timedelta(hours=1))


def no_google(e, eid, tag="inatel-sync"):
    return dict(e.corpo(tag=tag), id=eid)


def rodar(api, desejados, prefixos=("aula|",), **kw):
    import logging
    return sincronizar(api, "cal", desejados, prefixos, inicio_do_dia(AGORA.date()),
                       log=logging.getLogger("inatel_sync.teste"), agora=AGORA, **kw)


def test_cria_atualiza_e_nao_mexe_no_igual():
    igual, mudou = evento("aula|1"), evento("aula|2")
    api = AgendaFalsa([no_google(igual, "a"), no_google(evento("aula|2", titulo="antigo"), "b")])
    r = rodar(api, [igual, mudou, evento("aula|3")])
    assert (r.criados, r.atualizados, r.removidos) == (1, 1, 0)
    assert api.eventos["b"]["summary"] == "aula|2"


def test_so_apaga_os_proprios_prefixos():
    api = AgendaFalsa([no_google(evento("aula|velha"), "a"), no_google(evento("moodle|x"), "m")])
    r = rodar(api, [])  # prefixos = aula| -> moodle| e de outra integracao
    assert r.removidos == 1
    assert "m" in api.eventos and "a" not in api.eventos


def test_nunca_toca_evento_sem_a_tag():
    api = AgendaFalsa([no_google(evento("aula|cli"), "c", tag="agenda-cli")])
    r = rodar(api, [])
    assert r.removidos == 0 and "c" in api.eventos


def test_nao_apaga_evento_que_ja_comecou():
    hoje_cedo = evento("aula|cedo", n=0, hora=8)  # 08h, agora sao 12h
    api = AgendaFalsa([no_google(hoje_cedo, "x")])
    assert rodar(api, []).removidos == 0


def test_trava_segura_apagar_em_massa():
    existentes = [no_google(evento(f"aula|{i}", n=i + 1), str(i)) for i in range(20)]
    api = AgendaFalsa(existentes)
    r = rodar(api, [evento("aula|0", n=1)])  # fonte devolveu 1 de 20: parece lista parcial
    assert r.retidos == 19 and r.removidos == 0 and len(api.eventos) == 20


def test_trava_deixa_passar_poucos_e_forcar_passa():
    existentes = [no_google(evento(f"aula|{i}", n=i + 1), str(i)) for i in range(20)]
    assert rodar(AgendaFalsa(existentes), [evento(f"aula|{i}", n=i + 1) for i in range(16)]).removidos == 4
    assert rodar(AgendaFalsa(existentes), [], forcar=True).removidos == 20


def test_prefixos_vazios_nao_faz_nada():
    api = AgendaFalsa([no_google(evento("aula|1"), "a")])
    r = rodar(api, [], prefixos=())
    assert r.removidos == 0 and not api.aplicadas


def test_dry_run_nao_aplica():
    api = AgendaFalsa([no_google(evento("aula|velha"), "a")])
    r = rodar(api, [evento("aula|nova")], dry_run=True)
    assert (r.criados, r.removidos) == (1, 1) and not api.aplicadas


def test_chave_duplicada_fica_uma_so():
    e = evento("aula|1")
    api = AgendaFalsa([no_google(e, "a"), no_google(e, "b")])
    r = rodar(api, [e])
    assert r.removidos == 1 and len(api.eventos) == 1


def test_dia_inteiro_e_comparavel_normaliza_fuso():
    e = Evento(chave="moodle|x", titulo="Entrega", dia=dia(1), ultimo_dia=dia(3))
    corpo = e.corpo()
    assert corpo["start"] == {"date": "2026-11-03"} and corpo["end"] == {"date": "2026-11-06"}
    a = evento("aula|1").corpo()
    b = dict(a, start={"dateTime": "2026-11-03T22:00:00Z"}, end={"dateTime": "2026-11-03T23:00:00Z"})
    assert comparavel(a) == comparavel(b)  # o Google pode devolver em UTC
