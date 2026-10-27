"""Aviso de lembrete: janelinha no canto da tela, com Concluir e Adiar.

Aparece por cima das outras janelas sem roubar o foco do teclado. Fica na tela até
você agir (concluir, adiar ou fechar)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout

from . import tema

# (texto do menu, minutos). None = amanhã de manhã.
OPCOES_SONECA: list[tuple[str, int | None]] = [
    ("5 minutos", 5), ("10 minutos", 10), ("30 minutos", 30), ("1 hora", 60),
    ("3 horas", 180), ("Amanhã de manhã", None),
]


class AvisoLembrete(QFrame):
    concluir = Signal(int)
    adiar = Signal(int, object)     # (tarefa_id, minutos ou None para "amanhã")
    fechado = Signal(object)        # o próprio aviso

    LARGURA = 340

    def __init__(self, tarefa_id: int, titulo: str, texto: str):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.tarefa_id = tarefa_id
        self.setObjectName("aviso")
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)   # cantos arredondados de verdade
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(tema.qss())
        self.setFixedWidth(self.LARGURA)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(4)
        self.rotulo_titulo = QLabel(titulo)
        self.rotulo_titulo.setObjectName("avisoTitulo")
        self.rotulo_titulo.setWordWrap(True)
        lay.addWidget(self.rotulo_titulo)
        self.rotulo_texto = QLabel(texto)
        self.rotulo_texto.setObjectName("avisoTexto")
        lay.addWidget(self.rotulo_texto)
        lay.addSpacing(10)

        linha = QHBoxLayout()
        linha.setSpacing(8)
        self.btn_concluir = QPushButton("Concluir")
        self.btn_adiar = QPushButton("Adiar")
        self.btn_fechar = QPushButton("Fechar")
        for b in (self.btn_concluir, self.btn_adiar, self.btn_fechar):
            b.setCursor(Qt.PointingHandCursor)
            linha.addWidget(b)
        lay.addLayout(linha)

        self.menu_adiar = QMenu(self)
        for nome, minutos in OPCOES_SONECA:
            self.menu_adiar.addAction(nome, lambda m=minutos: self._adiar(m))
        self.btn_adiar.setMenu(self.menu_adiar)
        self.btn_concluir.clicked.connect(lambda: self._agir(lambda: self.concluir.emit(self.tarefa_id)))
        self.btn_fechar.clicked.connect(lambda: self._agir(lambda: None))

    def _adiar(self, minutos):
        self._agir(lambda: self.adiar.emit(self.tarefa_id, minutos))

    def _agir(self, acao):
        acao()
        self.fechar()

    def fechar(self):
        self.hide()
        self.fechado.emit(self)
        self.deleteLater()


class GerenteAvisos:
    """Empilha os avisos no canto inferior direito. Um aviso por tarefa."""

    MARGEM = 18
    ENTRE = 10

    def __init__(self, ao_concluir, ao_adiar):
        self._ao_concluir, self._ao_adiar = ao_concluir, ao_adiar
        self.avisos: list[AvisoLembrete] = []

    def mostrar(self, tarefa_id: int, titulo: str, texto: str, exibir: bool = True) -> AvisoLembrete:
        for velho in [a for a in self.avisos if a.tarefa_id == tarefa_id]:
            velho.fechar()            # o mais novo substitui o anterior da mesma tarefa
        aviso = AvisoLembrete(tarefa_id, titulo, texto)
        aviso.concluir.connect(self._ao_concluir)
        aviso.adiar.connect(self._ao_adiar)
        aviso.fechado.connect(self._removido)
        self.avisos.append(aviso)
        if exibir:
            aviso.show()
        self._posicionar()
        return aviso

    def _removido(self, aviso):
        if aviso in self.avisos:
            self.avisos.remove(aviso)
        self._posicionar()

    def _posicionar(self):
        tela = QGuiApplication.primaryScreen()
        if tela is None:
            return
        area = tela.availableGeometry()
        y = area.bottom() - self.MARGEM
        for aviso in reversed(self.avisos):
            aviso.adjustSize()
            y -= aviso.height()
            aviso.move(area.right() - self.MARGEM - aviso.width(), y)
            y -= self.ENTRE
