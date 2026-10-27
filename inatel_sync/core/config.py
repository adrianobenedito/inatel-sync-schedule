"""config.toml: um arquivo so, validado na carga. Segredos nunca entram aqui (ficam no keyring)."""

import copy
import datetime as dt
import re
import tomllib

import tomli_w

from inatel_sync.core import paths
from inatel_sync.core.erros import ErroConfig
from inatel_sync.core.trava import gravar_atomico

CORES = {"lavanda": "1", "salvia": "2", "roxo": "3", "rosa": "4", "amarelo": "5", "laranja": "6",
         "turquesa": "7", "cinza": "8", "azul": "9", "verde": "10", "vermelho": "11"}

PADRAO = {
    "versao": 1,
    "trava": {"max_apagar": 5, "max_apagar_pct": 30},
    "portal": {
        "ativo": False, "provas": True, "aulas": True,
        "login": "", "matricula": "", "curso": "",
        "agenda": "Inatel - Aulas e Provas", "cor_provas": "vermelho", "cor_aulas": "amarelo",
        "fim_aulas": "", "sem_aula": [],
        "horarios": ["07:00", "13:00", "18:00"],
    },
    "moodle": {
        "ativo": False, "fontes": [],
        "agenda": "Inatel - Aulas e Provas", "cor": "laranja",
        "horarios": ["07:00", "13:00", "18:00"],
    },
    "outlook": {
        "ativo": False, "agenda": "Trabalho", "cor": "cinza", "dias": 60,
        "abrir_se_fechado": True, "espera_s": 60,
        "a_cada_min": 30, "janela": ["07:00", "22:00"],
    },
    "cli": {"agenda": True, "tarefas": True},
}

_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _mesclar(base, novo):
    out = copy.deepcopy(base)
    for k, v in novo.items():
        out[k] = _mesclar(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _data(v):
    try:
        dt.date.fromisoformat(v)
        return True
    except (TypeError, ValueError):
        return False


def validar(cfg):
    erros = []

    def tipo(secao, chave, t, nome):
        v = cfg.get(secao, {}).get(chave)
        if not isinstance(v, t) or (t is int and isinstance(v, bool)):
            erros.append(f"[{secao}] {chave} deve ser {nome} (esta: {v!r})")
            return None
        return v

    for secao in ("portal", "moodle", "outlook", "cli"):
        if not isinstance(cfg.get(secao), dict):
            erros.append(f"secao [{secao}] invalida")
    if erros:
        return erros
    for secao in ("portal", "moodle", "outlook"):
        tipo(secao, "ativo", bool, "true/false")
        if tipo(secao, "agenda", str, "texto") == "":
            erros.append(f"[{secao}] agenda nao pode ficar vazia")
        for chave in [c for c in cfg[secao] if c.startswith("cor")]:
            if cfg[secao][chave] not in CORES and cfg[secao][chave] not in CORES.values():
                erros.append(f"[{secao}] {chave} = {cfg[secao][chave]!r}: use uma de {', '.join(CORES)}")
        for h in cfg[secao].get("horarios", []):
            if not isinstance(h, str) or not _HORA.match(h):
                erros.append(f"[{secao}] horario {h!r} invalido (use HH:MM)")

    p = cfg["portal"]
    if p["ativo"]:
        if not str(p.get("login", "")).strip():
            erros.append("[portal] login vazio: rode inatel-sync setup")
        if not re.fullmatch(r"\d+", str(p.get("curso", ""))):
            erros.append("[portal] curso deve ser o codigo numerico do curso (rode inatel-sync setup para escolher pela lista)")
    if p.get("fim_aulas") and not _data(p["fim_aulas"]):
        erros.append(f"[portal] fim_aulas {p['fim_aulas']!r} invalido (use AAAA-MM-DD)")
    for d in p.get("sem_aula", []):
        if not _data(d):
            erros.append(f"[portal] sem_aula: {d!r} invalido (use AAAA-MM-DD)")

    m = cfg["moodle"]
    for f in m.get("fontes", []):
        if f not in ("moodle", "code"):
            erros.append(f"[moodle] fonte {f!r} desconhecida (use moodle e/ou code)")
    if m["ativo"] and not m.get("fontes"):
        erros.append("[moodle] ativo sem nenhuma fonte (moodle, code)")

    o = cfg["outlook"]
    tipo("outlook", "dias", int, "numero de dias")
    tipo("outlook", "espera_s", int, "segundos")
    if tipo("outlook", "a_cada_min", int, "minutos") is not None and o["a_cada_min"] < 5:
        erros.append("[outlook] a_cada_min minimo e 5")
    j = o.get("janela", [])
    if not (isinstance(j, list) and len(j) == 2 and all(isinstance(h, str) and _HORA.match(h) for h in j)):
        erros.append('[outlook] janela deve ser ["HH:MM", "HH:MM"]')

    t = cfg.get("trava", {})
    if not isinstance(t.get("max_apagar"), int) or not isinstance(t.get("max_apagar_pct"), int):
        erros.append("[trava] max_apagar e max_apagar_pct devem ser numeros inteiros")
    return erros


def carregar(caminho=None, exigir=True):
    caminho = caminho or paths.arquivo_config()
    if not caminho.exists():
        if exigir:
            raise ErroConfig(f"Configuracao nao encontrada em {caminho}. Rode: inatel-sync setup")
        return copy.deepcopy(PADRAO)
    try:
        dados = tomllib.loads(caminho.read_text(encoding="utf-8-sig"))
    except tomllib.TOMLDecodeError as e:
        raise ErroConfig(f"{caminho.name} invalido: {e}") from None
    cfg = _mesclar(PADRAO, dados)
    erros = validar(cfg)
    if erros:
        raise ErroConfig(f"{caminho.name} com problemas:\n  - " + "\n  - ".join(erros))
    return cfg


def salvar(cfg, caminho=None):
    erros = validar(cfg)
    if erros:
        raise ErroConfig("configuracao invalida:\n  - " + "\n  - ".join(erros))
    gravar_atomico(caminho or paths.arquivo_config(), tomli_w.dumps(cfg))


def cor_id(nome):
    return CORES.get(nome, nome)


def definir(cfg, caminho_chave, texto):
    """inatel-sync config set secao.chave valor: converte o texto para o tipo do valor atual."""
    secao, _, chave = caminho_chave.partition(".")
    if secao not in cfg or not isinstance(cfg[secao], dict) or not chave:
        raise ErroConfig(f"chave desconhecida: {caminho_chave} (formato: secao.chave)")
    atual = cfg[secao].get(chave)
    if isinstance(atual, bool):
        valor = texto.lower() in ("1", "true", "sim", "s", "on", "yes")
    elif isinstance(atual, int):
        valor = int(texto)
    elif isinstance(atual, list):
        valor = [v.strip() for v in texto.split(",") if v.strip()]
    else:
        valor = texto
    cfg[secao][chave] = valor
    return valor
