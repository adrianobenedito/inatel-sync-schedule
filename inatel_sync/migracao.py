"""Importa uma instalacao da versao 1 (scripts soltos: config.json, state.json, token.json).

As chaves e tags dos eventos nao mudaram, entao os eventos existentes continuam reconhecidos.
Nada e apagado: o token.json vira token.json.migrado depois de ir para o keyring.
"""

import json
from pathlib import Path

from inatel_sync.core import config as cfgmod
from inatel_sync.core import estado, log, paths, segredos
from inatel_sync.integracoes.moodle import FONTES

_log = log.logger("migracao")


def _ler(p):
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else {}


def importar_v1(pasta):
    pasta = Path(pasta).resolve()
    antigo = _ler(pasta / "config.json")
    if not antigo:
        _log.error("config.json da versao 1 nao encontrado em %s", pasta)
        return 2

    cfg = cfgmod.carregar(exigir=False)
    p = cfg["portal"]
    p.update(ativo=True, login=antigo.get("login", antigo["matricula"]), matricula=antigo["matricula"],
             curso=str(antigo["curso"]), agenda=antigo.get("nome_agenda", p["agenda"]),
             fim_aulas=antigo.get("fim_aulas", ""),
             sem_aula=sorted(set(antigo.get("sem_aula", [])) | set(antigo.get("feriados_extra", []))))
    fontes = [f for f, (usuario, *_ ) in FONTES.items() if segredos.ler(segredos.MOODLE, usuario)]
    cfg["moodle"].update(ativo=bool(fontes), fontes=fontes, agenda=p["agenda"])
    cfg["outlook"].update(ativo=(pasta / "sync_outlook.py").exists(),
                          agenda=antigo.get("nome_agenda_trabalho", cfg["outlook"]["agenda"]))
    if not segredos.ler(segredos.PORTAL, p["matricula"]):
        _log.warning("Senha do portal nao encontrada no keyring; rode: inatel-sync config senha")
    cfgmod.salvar(cfg)
    _log.info("config.toml criado em %s", paths.arquivo_config())

    # ids das agendas, pelo nome (a versao 1 guardava por chave fixa)
    st = _ler(pasta / "state.json")
    nomes = {"calendar_id": p["agenda"], "calendar_id_trabalho": cfg["outlook"]["agenda"]}
    agendas = {nomes.get(k, k.removeprefix("calendar_id_")): v for k, v in st.items() if k.startswith("calendar_id")}
    estado.atualizar(lambda est: est.setdefault("agendas", {}).update(agendas))
    _log.info("Agendas importadas: %s", ", ".join(agendas))

    token = pasta / "token.json"
    if token.exists():
        segredos.gravar(segredos.GOOGLE, "token", token.read_text(encoding="utf-8"))
        token.rename(token.with_name("token.json.migrado"))
        _log.info("Token do Google movido para o Gerenciador de Credenciais (token.json -> token.json.migrado)")
    elif not segredos.ler(segredos.GOOGLE, "token"):
        _log.warning("Sem token do Google; rode: inatel-sync auth")

    cliente = pasta / "client_secret.json"
    destino = paths.pasta_dados() / "client_secret.json"
    if cliente.exists() and not destino.exists():
        destino.write_bytes(cliente.read_bytes())  # app OAuth da propria pessoa: usado no proximo auth
    return 0
