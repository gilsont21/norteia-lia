"""Preferências simples (tema escolhido), em JSON na pasta do usuário."""
from __future__ import annotations

import json
from pathlib import Path

from .marca import PASTA_DADOS

PASTA = Path.home() / PASTA_DADOS
ARQUIVO = PASTA / "config.json"


def carregar() -> dict:
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def salvar(dados: dict) -> None:
    try:
        PASTA.mkdir(exist_ok=True)
        ARQUIVO.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # preferência não é crítica
