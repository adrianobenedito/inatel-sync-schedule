import importlib.util
import io
import zipfile
from pathlib import Path

import pytest

from inatel_sync import setup
from inatel_sync.integracoes import portal

_spec = importlib.util.spec_from_file_location("build", Path(__file__).parent.parent / "scripts" / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)


TERMOS = ["98765432", "432", "fulano", "empresax", "10.9.", "fulano.tal"]  # ficticios


def _zip(caminho, arquivos):
    with zipfile.ZipFile(caminho, "w") as zf:
        for nome, conteudo in arquivos.items():
            zf.writestr(nome, conteudo)


def _wheel(arquivos):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for nome, conteudo in arquivos.items():
            zf.writestr(nome, conteudo)
    return buf.getvalue()


def test_varredura_limpa(tmp_path):
    z = tmp_path / "ok.zip"
    _zip(z, {"x/README.md": "Google token no keyring", "x/pacote/a.whl": _wheel({"inatel_sync/cli.py": "print(1)"}),
             "x/uv.exe": b"\x00432\x00"})  # numero curto solto em binario e ruido
    assert build.varrer(z, TERMOS) == []


@pytest.mark.parametrize("arquivos, esperado", [
    ({"x/a.md": "matricula 98765432"}, "98765432"),
    ({"x/a.md": "login 432 no portal"}, "'432'"),
    ({"x/pacote/a.whl": _wheel({"inatel_sync/c.py": "# Fulano"})}, "fulano"),
    ({"x/a.md": "ip 10.9.1.1"}, "10.9."),
    ({"x/token.json": "{}"}, "arquivo proibido"),
    ({"x/logs/sync.log": ""}, "arquivo proibido"),
    ({"x/plugins/gmud.py": ""}, "arquivo proibido"),
    ({"x/d/c.json": '{"refresh_token": "x"}'}, "token do Google"),
])
def test_varredura_acha_dado_pessoal(tmp_path, arquivos, esperado):
    z = tmp_path / "ruim.zip"
    _zip(z, arquivos)
    assert any(esperado in p for p in build.varrer(z, TERMOS))


def test_numero_casa_inteiro(tmp_path):
    z = tmp_path / "n.zip"
    _zip(z, {"x/a.md": "versao 4321 e 1.432"})
    assert build.varrer(z, ["432"]) == []


def test_login_tenta_matricula_curta(monkeypatch):
    tentados = []

    def entrar(login, curso, senha):
        tentados.append(login)
        if login != "123":
            raise portal.LoginRecusado("recusado")

    monkeypatch.setattr(portal, "entrar", entrar)
    assert setup._testar_login("14300123", "143", "s") == "123"
    assert tentados == ["14300123", "123"]
    tentados.clear()
    assert setup._testar_login("99", "143", "s") is None and tentados == ["99"]
