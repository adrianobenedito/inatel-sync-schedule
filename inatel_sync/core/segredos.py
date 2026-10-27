"""Segredos so no Gerenciador de Credenciais do Windows (keyring/DPAPI), nunca em arquivo."""

import os

import keyring
from keyring.errors import PasswordDeleteError

PORTAL = "inatel-portal"  # usuario: matricula (ou login)
MOODLE = "inatel-moodle"  # usuarios: ical, ical-code
GOOGLE = "inatel-sync-google"  # usuario: token


def _servico(nome):
    # INATEL_SYNC_KEYRING_SUFIXO separa uma instalacao de teste da real
    return nome + os.environ.get("INATEL_SYNC_KEYRING_SUFIXO", "")


def ler(servico, usuario):
    return keyring.get_password(_servico(servico), usuario)


def gravar(servico, usuario, valor):
    keyring.set_password(_servico(servico), usuario, valor)


def apagar(servico, usuario):
    try:
        keyring.delete_password(_servico(servico), usuario)
        return True
    except PasswordDeleteError:
        return False
