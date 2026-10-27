"""Registro das integracoes: as do pacote e os plugins locais (%APPDATA%\\inatel-sync\\plugins\\*.py)."""

import importlib.util

from inatel_sync.core import log, paths


def _embutidas():
    from inatel_sync.integracoes.moodle import Moodle
    from inatel_sync.integracoes.outlook import Outlook
    from inatel_sync.integracoes.portal import Portal

    return [Portal, Moodle, Outlook]


def _plugins():
    pasta = paths.pasta_plugins()
    classes = []
    for arq in sorted(pasta.glob("*.py")) if pasta.exists() else []:
        try:
            spec = importlib.util.spec_from_file_location(f"inatel_sync_plugin_{arq.stem}", arq)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            classes.append(mod.INTEGRACAO)
        except Exception as e:
            log.logger().warning("Plugin %s ignorado: %s", arq.name, e)
    return classes


def todas(cfg):
    """{nome: instancia} de todas as integracoes conhecidas (ativas ou nao)."""
    return {c.nome: c(cfg) for c in _embutidas() + _plugins()}
