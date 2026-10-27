"""Atalho global do Windows (funciona com o app na bandeja) e a janelinha de tarefa rápida.

O atalho usa a API RegisterHotKey do Windows. Em outros sistemas, ou se outro programa já usa a
combinação, `registrar()` devolve False e o app segue normal (a janelinha também abre pelo menu da bandeja).
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, Qt, Signal
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QVBoxLayout

from . import tema

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x4000
ID_ATALHO = 0x7A51
TECLA_N = 0x4E


class FiltroDeAtalho(QAbstractNativeEventFilter):
    def __init__(self, ao_apertar):
        super().__init__()
        self.ao_apertar = ao_apertar
        self.registrado = False

    def registrar(self, modificadores: int = MOD_CONTROL | MOD_ALT, tecla: int = TECLA_N) -> bool:
        if not sys.platform.startswith("win"):
            return False
        try:
            import ctypes
            ok = bool(ctypes.windll.user32.RegisterHotKey(None, ID_ATALHO, modificadores | MOD_NOREPEAT, tecla))
        except (AttributeError, OSError):
            return False
        if ok:
            app = QCoreApplication.instance()
            if app is not None:
                app.installNativeEventFilter(self)
            self.registrado = True
        return ok

    def liberar(self) -> None:
        if self.registrado and sys.platform.startswith("win"):
            import ctypes
            ctypes.windll.user32.UnregisterHotKey(None, ID_ATALHO)
            self.registrado = False

    def nativeEventFilter(self, tipo, mensagem):
        if sys.platform.startswith("win") and tipo in (b"windows_generic_MSG", "windows_generic_MSG"):
            import ctypes
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(int(mensagem))
            if msg.message == WM_HOTKEY and msg.wParam == ID_ATALHO:
                self.ao_apertar()
                return True, 0
        return False, 0


class JanelaRapida(QDialog):
    """Caixinha no meio da tela: digitou, Enter, a tarefa entra na Caixa de Entrada."""

    criada = Signal(object)

    def __init__(self, servico, parent=None):
        super().__init__(parent)
        self.servico = servico
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setModal(False)
        self.setFixedWidth(560)
        pal = tema.atual
        self.setStyleSheet(f"QDialog {{ background: {pal.barra}; border: 1px solid {pal.borda}; border-radius: 12px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(8)
        titulo = QLabel("Nova tarefa")
        titulo.setObjectName("secao")
        lay.addWidget(titulo)
        self.campo = QLineEdit()
        self.campo.setObjectName("entrada")
        self.campo.setStyleSheet("padding-left: 14px;")
        self.campo.setPlaceholderText("ex.: Pagar conta amanhã às 9h !2 #casa     (Enter adiciona, Esc fecha)")
        lay.addWidget(self.campo)
        self.campo.returnPressed.connect(self.adicionar)

    def adicionar(self):
        texto = self.campo.text().strip()
        if not texto:
            return None
        t = self.servico.adicionar_rapido(texto)
        self.campo.clear()
        self.criada.emit(t)
        self.close()
        return t

    def mostrar(self):
        self.campo.clear()
        self.show()
        self.raise_()
        self.activateWindow()
        self.campo.setFocus()
        tela = self.screen().availableGeometry() if self.screen() else None
        if tela is not None:
            self.move(tela.center().x() - self.width() // 2, tela.top() + tela.height() // 4)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(e)
