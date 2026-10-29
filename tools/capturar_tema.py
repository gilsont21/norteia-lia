"""Capturas dos temas, do fundo ilustrado e da janela de Configurações (dados de demonstração).

Uso: python tools/capturar_tema.py <pasta_saida>
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from norteia.core import Banco, Servico  # noqa: E402
from norteia.core.ia_provedores import CofreIA, ConfigIA  # noqa: E402
from norteia.demo import popular  # noqa: E402
from norteia.ui.configuracoes import JanelaConfiguracoes  # noqa: E402
from norteia.ui.janela import JanelaPrincipal  # noqa: E402


def _janela(prefs: dict) -> JanelaPrincipal:
    svc = Servico(Banco(":memory:"), pasta_dados=Path(tempfile.mkdtemp()))
    svc._extras["ia"] = ConfigIA(svc.banco, CofreIA(svc.banco, usar_keyring=False))
    popular(svc)
    j = JanelaPrincipal(svc, notificador=lambda t, x: None, prefs=prefs, google_em_thread=False)
    j.resize(1280, 800)
    j.show()
    return j


def main(saida: Path) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])

    def foto(w, nome):
        app.processEvents()
        w.grab().save(str(saida / nome))

    j = _janela({})
    for modo in ("escuro", "claro"):
        j.aplicar_preferencias({"tema_modo": modo, "tema_cor": "padrao", "tema_fundo": ""})
        d = JanelaConfiguracoes(j, "aparencia")
        d.resize(980, 700)
        d.show()
        foto(d, f"config-aparencia-{modo}.png")
        d.close()
    for secao in ("geral", "notificacoes", "integracoes", "atalhos", "sobre"):
        d = JanelaConfiguracoes(j, secao)
        d.show()
        foto(d, f"config-{secao}.png")
        d.close()
    for cor, modo, fundo in (("padrao", "claro", "primavera"), ("ceu", "claro", "verao"), ("ambar", "claro", "outono"),
                             ("lilas", "escuro", "inverno"), ("turquesa", "escuro", "verao"), ("ebano", "escuro", "")):
        j.aplicar_preferencias({"tema_cor": cor, "tema_modo": modo, "tema_fundo": fundo})
        j.mostrar_pagina("tarefas")
        foto(j, f"tarefas-{cor}-{modo}-{fundo or 'semfundo'}.png")
    j.aplicar_preferencias({"tema_cor": "rosa", "tema_modo": "claro", "tema_fundo": ""})
    for pagina in ("calendario", "matriz", "foco", "habitos", "estatisticas", "ia"):
        j.mostrar_pagina(pagina)
        foto(j, f"pagina-{pagina}-claro.png")
    j.mostrar_pagina("tarefas")
    j.pagina_calendario  # noqa: B018
    j.close()


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "capturas"))
