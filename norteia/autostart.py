"""Abrir junto com o Windows (e continuar na bandeja), para os lembretes nunca falharem.

No Windows isso é uma entrada em HKEY_CURRENT_USER\\...\\Run: não pede administrador e dá para
desligar a qualquer momento. Em outros sistemas não faz nada."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings

from .marca import NOME as NOME_ATUAL

CHAVE = r"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run"
NOME = NOME_ATUAL
NOME_ANTIGO = "Tarefas"       # nome da entrada nas versões anteriores: continua sendo reconhecido e limpo


def disponivel() -> bool:
    return sys.platform == "win32"


def comando(executavel: str | None = None, script: Path | None = None) -> str:
    """Linha de comando gravada no registro. Programa empacotado (.exe) ou Python + main.py."""
    executavel = executavel or sys.executable
    if getattr(sys, "frozen", False):
        return f'"{executavel}" --minimizado'
    # pythonw não abre janela preta de terminal
    executavel = executavel.replace("python.exe", "pythonw.exe")
    script = script or Path(__file__).resolve().parent.parent / "main.py"
    return f'"{executavel}" "{script}" --minimizado'


def _config(configuracao: QSettings | None) -> QSettings | None:
    if configuracao is not None:
        return configuracao
    return QSettings(CHAVE, QSettings.NativeFormat) if disponivel() else None


def ligado(configuracao: QSettings | None = None) -> bool:
    c = _config(configuracao)
    return bool(c and (c.contains(NOME) or c.contains(NOME_ANTIGO)))


def definir(sim: bool, configuracao: QSettings | None = None, linha: str | None = None) -> None:
    c = _config(configuracao)
    if c is None:
        return
    c.remove(NOME_ANTIGO)
    if sim:
        c.setValue(NOME, linha or comando())
    else:
        c.remove(NOME)
    c.sync()
