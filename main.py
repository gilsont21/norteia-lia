"""Ponto de entrada. Uso:  python main.py          (usa o banco real)
                          python main.py --demo   (banco temporário com dados de exemplo)"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox

from norteia import autostart, config
from norteia.marca import NOME, PASTA_DADOS
from norteia.core import Banco, Servico
from norteia.sync import Sincronizador
from norteia.sync.cliente import transporte_http
from norteia.demo import popular
from norteia.ui.atalho_global import FiltroDeAtalho
from norteia.ui.janela import JanelaPrincipal


def criar_servico(demo: bool) -> Servico:
    if demo:
        svc = Servico(Banco(":memory:"))
        popular(svc)
        return svc
    pasta = Path.home() / PASTA_DADOS
    pasta.mkdir(exist_ok=True)
    return Servico(Banco(pasta / "tarefas.db"), pasta_dados=pasta)


def main() -> int:
    app = QApplication(sys.argv)
    demo = "--demo" in sys.argv
    trava = None
    if not demo:  # só uma cópia por vez, senão os avisos tocariam em dobro
        pasta = Path.home() / PASTA_DADOS
        pasta.mkdir(exist_ok=True)
        trava = QLockFile(str(pasta / "tarefas.lock"))
        if not trava.tryLock(100):
            QMessageBox.information(None, NOME, f"O {NOME} já está aberto. "
                                    "Procure o ícone perto do relógio (bandeja do sistema).")
            return 0
    servico = criar_servico(demo)
    prefs = config.carregar()
    prefs.setdefault("fechar_para_bandeja", True)
    prefs["iniciar_com_windows"] = autostart.ligado()
    app.setQuitOnLastWindowClosed(not prefs["fechar_para_bandeja"] or demo)
    prefs.setdefault("aviso_na_tela", True)
    prefs.setdefault("resumo_diario", True)
    prefs.setdefault("resumo_hora", "08:00")

    def montar_sincronizador(url: str, token: str):
        prefs["servidor_url"], prefs["servidor_token"] = url, token
        config.salvar(prefs)
        if url and token:
            return Sincronizador(servico.banco, transporte_http(url, token))
        return None

    montar_sincronizador.atual = lambda: (prefs.get("servidor_url", ""), prefs.get("servidor_token", ""))
    sincronizador = None
    if "--demo" not in sys.argv and prefs.get("servidor_url") and prefs.get("servidor_token"):
        sincronizador = Sincronizador(servico.banco, transporte_http(prefs["servidor_url"], prefs["servidor_token"]))
    janela = JanelaPrincipal(servico, sincronizador=sincronizador, ao_configurar_sync=montar_sincronizador,
                             prefs=prefs, ao_salvar_prefs=config.salvar)
    if "--minimizado" in sys.argv and not demo:
        janela.iniciar_na_bandeja()
    else:
        janela.show()
    filtro = FiltroDeAtalho(janela.abrir_tarefa_rapida)
    if not demo:
        filtro.registrar()                      # Ctrl+Alt+N em qualquer programa (só no Windows)
    codigo = app.exec()
    filtro.liberar()
    if trava is not None:
        trava.unlock()
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
