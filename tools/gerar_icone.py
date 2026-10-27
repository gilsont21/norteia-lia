"""Gera windows/norteia.ico a partir do ícone desenhado em código (rodar uma vez, ou quando mudar o ícone)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QGuiApplication  # noqa: E402

from norteia.ui.janela import icone_do_app  # noqa: E402


def main() -> None:
    app = QGuiApplication([])
    destino = Path(__file__).resolve().parent.parent / "windows" / "norteia.ico"
    imagem = icone_do_app().pixmap(256, 256).toImage()
    if not imagem.save(str(destino), "ICO"):
        raise SystemExit("Não consegui gravar o .ico (falta o plugin de imagem ICO do Qt).")
    print("Gerado:", destino)
    del app


if __name__ == "__main__":
    main()
