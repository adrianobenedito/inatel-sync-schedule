"""Gera dist/inatel-sync-<versao>.zip e confere que nada pessoal foi junto.

Uso: uv run python scripts/build.py [--teste]
Precisa de instalador/client_secret.json do projeto Google publico do inatel-sync (nao o pessoal).
--teste: sem client_secret, gera build/inatel-sync-<versao>-teste.zip (so para testar a instalacao).
"""

import io
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
INSTALADOR = RAIZ / "instalador"
DADOS = RAIZ / "inatel_sync" / "dados"

# Termos pessoais que nunca podem ir no zip: um por linha em local/termos-proibidos.txt (fora do git, porque
# o repositorio e publico). Numeros casam como numero inteiro; termos curtos nao sao procurados em binarios.
# "token" aparece no codigo (keyring, variaveis): o que conta e arquivo de token/estado/log ou refresh_token.
TERMOS = RAIZ / "local" / "termos-proibidos.txt"
NOMES_PROIBIDOS = re.compile(r"(^|/)(token\.json|state\.json|estado[^/]*\.json|gmud_state\.json|config\.json|"
                             r"config\.toml|eventos\.json)$|\.log$|(^|/)local/|(^|/)plugins/", re.I)
BINARIOS = (".exe", ".pyd", ".dll")


def carregar_termos(arquivo=TERMOS):
    if not arquivo.exists():
        sys.exit(f"Falta {arquivo.relative_to(RAIZ)}: um termo pessoal por linha (matricula, nome, e-mail...).")
    termos = [t.strip().lower() for t in arquivo.read_text(encoding="utf-8").splitlines()]
    return [t for t in termos if t and not t.startswith("#")]


def _padrao(termo):
    p = re.escape(termo)
    return rf"(?<![\d.]){p}(?!\d)" if termo.isdigit() else p


def versao():
    texto = (RAIZ / "inatel_sync" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__ = "([^"]+)"', texto).group(1)


def _client_id(arquivo):
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    return (dados.get("installed") or dados.get("web") or {}).get("client_id")


def conferir_client_secret():
    publico = INSTALADOR / "client_secret.json"
    if not publico.exists():
        sys.exit("Falta instalador/client_secret.json (projeto Google publico do inatel-sync).")
    pessoal = RAIZ / "client_secret.json"
    if pessoal.exists() and _client_id(pessoal) == _client_id(publico):
        sys.exit("instalador/client_secret.json e o do projeto PESSOAL. Use o do projeto publico.")
    return publico


def gerar_wheel(client_secret, destino):
    DADOS.mkdir(exist_ok=True)
    if client_secret:
        shutil.copy2(client_secret, DADOS / "client_secret.json")
    try:
        subprocess.run(["uv", "build", "--wheel", "--out-dir", str(destino)], cwd=RAIZ, check=True)
    finally:
        shutil.rmtree(DADOS)
    return next(destino.glob("inatel_sync-*.whl"))


def _arquivos(zf, prefixo=""):
    """(nome, bytes) de tudo no zip, abrindo o wheel que vai dentro."""
    for nome in zf.namelist():
        dados = zf.read(nome)
        yield prefixo + nome, dados
        if nome.endswith(".whl"):
            with zipfile.ZipFile(io.BytesIO(dados)) as interno:
                yield from _arquivos(interno, prefixo + nome + "!/")


def varrer(zip_path, termos):
    problemas = []
    with zipfile.ZipFile(zip_path) as zf:
        for nome, dados in _arquivos(zf):
            if NOMES_PROIBIDOS.search(nome):
                problemas.append(f"arquivo proibido: {nome}")
            texto = dados.decode("utf-8", errors="ignore").lower()
            binario = nome.lower().endswith(BINARIOS)
            for termo in termos:
                if binario and len(termo) < 5:
                    continue  # numero curto solto num .exe e ruido
                if re.search(_padrao(termo), texto):
                    problemas.append(f"'{termo}' em {nome}")
            if nome.endswith(".json") and b'"refresh_token"' in dados:
                problemas.append(f"token do Google em {nome}")
    return problemas


def main():
    v = versao()
    teste = "--teste" in sys.argv
    termos = carregar_termos()
    client_secret = None if teste else conferir_client_secret()
    build = RAIZ / "build"
    shutil.rmtree(build, ignore_errors=True)
    wheel = gerar_wheel(client_secret, build / "pacote")
    uv = shutil.which("uv")
    if not uv:
        sys.exit("uv nao encontrado no PATH.")
    dist = build if teste else RAIZ / "dist"
    dist.mkdir(exist_ok=True)
    zip_path = dist / f"inatel-sync-{v}{'-teste' if teste else ''}.zip"
    pasta = f"inatel-sync-{v}/"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(INSTALADOR / "install.cmd", pasta + "install.cmd")
        zf.write(INSTALADOR / "uninstall.cmd", pasta + "uninstall.cmd")
        zf.write(uv, pasta + "uv.exe")
        zf.write(wheel, pasta + "pacote/" + wheel.name)
        zf.write(RAIZ / "README.md", pasta + "README.md")
        zf.write(RAIZ / "CHANGELOG.md", pasta + "CHANGELOG.md")
        zf.write(RAIZ / "inatel_sync" / "docs" / "teams-power-automate.md", pasta + "docs/teams-power-automate.md")
    problemas = varrer(zip_path, termos)
    if problemas:
        zip_path.unlink()
        sys.exit("Zip descartado, achei dados pessoais:\n  " + "\n  ".join(problemas))
    print(f"{zip_path} ({zip_path.stat().st_size // 1024} KB) - varredura limpa")


if __name__ == "__main__":
    main()
