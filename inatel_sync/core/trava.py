"""Uma execucao por vez (as tarefas do logon disparam juntas) e escrita atomica de arquivos."""

import contextlib
import msvcrt
import os
import time

from inatel_sync.core import paths
from inatel_sync.core.erros import Aviso


@contextlib.contextmanager
def trava(espera=180):
    f = open(paths.pasta_dados() / "trava.lock", "a+")
    inicio = time.monotonic()
    try:
        while True:
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() - inicio > espera:
                    raise Aviso(f"outra execucao do inatel-sync esta rodando ha mais de {espera // 60} min; pulando")
                time.sleep(1)
        try:
            yield
        finally:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        f.close()


def gravar_atomico(caminho, texto):
    """Grava num temporario e troca: quem le ao mesmo tempo nunca ve o arquivo pela metade."""
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, caminho)
