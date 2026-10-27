"""Busca flutuante (Ctrl+K): uma caixa no alto da janela que procura em tarefas, listas, etiquetas e filtros."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QStackedLayout,
                               QVBoxLayout, QWidget)

from ..core import servico as _srv
from . import icones, tema
from .popovers import Flutuante
from .util import rotulo_prazo

PAPEL_TIPO = Qt.UserRole + 1
PAPEL_VALOR = Qt.UserRole + 2
MAX_POR_GRUPO = 8


class Ilustracao(QWidget):
    """Lupa sobre um cartão: o desenho do estado vazio."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(150, 110)

    def paintEvent(self, _):
        pal = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        borda = QColor(pal.borda).lighter(130)
        p.setPen(QPen(borda, 2))
        p.setBrush(QColor(pal.campo))
        p.drawRoundedRect(QRectF(22, 14, 92, 76), 10, 10)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal.borda).lighter(160))
        for i, larg in enumerate((56, 70, 44)):
            p.drawRoundedRect(QRectF(34, 30 + i * 16, larg, 6), 3, 3)
        p.setPen(QPen(QColor(pal.destaque), 3.4, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(QColor(pal.barra))
        p.drawEllipse(QPointF(98, 66), 17, 17)
        p.drawLine(QPointF(110, 78), QPointF(125, 94))
        p.end()


class PainelBusca(Flutuante):
    """Digite e escolha: tarefa abre na lista dela; lista, etiqueta e filtro abrem a tela correspondente."""

    def __init__(self, janela):
        super().__init__(janela)
        self.janela = janela
        self.servico = janela.servico
        self.setFixedSize(580, 470)
        pal = tema.atual
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(8)
        cab = QLabel("Buscar")
        cab.setStyleSheet("font-size: 15px; font-weight: 700;")
        lay.addWidget(cab)
        self.campo = QLineEdit()
        self.campo.setObjectName("entrada")
        self.campo.setClearButtonEnabled(True)
        self.campo.setPlaceholderText("Pesquisar tarefas, etiquetas, listas e filtros")
        self.campo.addAction(icones.icone("busca", pal.apagado, 16), QLineEdit.LeadingPosition)
        self.campo.textChanged.connect(self.buscar)
        self.campo.installEventFilter(self)
        lay.addWidget(self.campo)

        corpo = QWidget()
        self.pilha = QStackedLayout(corpo)
        vazio = QWidget()
        vl = QVBoxLayout(vazio)
        vl.addStretch(1)
        vl.addWidget(Ilustracao(), 0, Qt.AlignHCenter)
        self.dica = QLabel("Pesquisar tarefas, etiquetas, listas e filtros")
        self.dica.setAlignment(Qt.AlignCenter)
        self.dica.setStyleSheet(f"color: {pal.apagado}; font-size: 13px;")
        vl.addWidget(self.dica)
        vl.addStretch(2)
        self.pilha.addWidget(vazio)
        self.lista = QListWidget()
        self.lista.setFrameShape(QListWidget.NoFrame)
        self.lista.setIconSize(QSize(16, 16))
        self.lista.setStyleSheet(
            f"QListWidget {{ background: transparent; outline: none; }} "
            f"QListWidget::item {{ padding: 7px 8px; border-radius: 6px; }} "
            f"QListWidget::item:selected {{ background: {pal.linha_selecionada}; color: {pal.texto}; }} "
            f"QListWidget::item:hover {{ background: {pal.linha_hover}; }}")
        self.lista.itemClicked.connect(self.ativar)
        self.pilha.addWidget(self.lista)
        lay.addWidget(corpo, 1)

    # ---- abrir/fechar ----
    def abrir(self, texto: str = ""):
        self.campo.setText(texto)
        self.buscar(texto)
        j = self.janela
        topo = j.mapToGlobal(j.rect().topLeft())
        x = topo.x() + (j.width() - self.width()) // 2
        y = topo.y() + max(40, j.height() // 9)
        self.move(x, y)
        self.show()
        self.raise_()
        self.campo.setFocus()

    def eventFilter(self, obj, ev):
        if obj is self.campo and ev.type() == QEvent.KeyPress:
            k = ev.key()
            if k in (Qt.Key_Down, Qt.Key_Up):
                self._mover(1 if k == Qt.Key_Down else -1)
                return True
            if k in (Qt.Key_Return, Qt.Key_Enter):
                item = self.lista.currentItem()
                if item is not None:
                    self.ativar(item)
                return True
            if k == Qt.Key_Escape:
                self.close()
                return True
        return super().eventFilter(obj, ev)

    def _mover(self, passo: int):
        n = self.lista.count()
        if not n:
            return
        i = self.lista.currentRow()
        while True:
            i += passo
            if i < 0 or i >= n:
                return
            if self.lista.item(i).data(PAPEL_TIPO) not in (None, "cabecalho"):
                self.lista.setCurrentRow(i)
                return

    # ---- resultados ----
    def _cabecalho(self, texto: str):
        it = QListWidgetItem(texto)
        it.setFlags(Qt.NoItemFlags)
        it.setData(PAPEL_TIPO, "cabecalho")
        f = it.font()
        f.setPixelSize(11)
        f.setBold(True)
        it.setFont(f)
        it.setForeground(QColor(tema.atual.apagado))
        self.lista.addItem(it)

    def _item(self, texto: str, icone: str, cor: str, tipo: str, valor, direita: str = ""):
        it = QListWidgetItem(icones.icone(icone, cor, 16), texto + (f"        {direita}" if direita else ""))
        it.setData(PAPEL_TIPO, tipo)
        it.setData(PAPEL_VALOR, valor)
        it.setToolTip(texto)
        self.lista.addItem(it)

    def buscar(self, texto: str):
        texto = texto.strip()
        self.lista.clear()
        if not texto:
            self.pilha.setCurrentIndex(0)
            return
        pal = tema.atual
        nome = texto.lstrip("#").lower()
        tarefas = self.servico.buscar(texto)[:MAX_POR_GRUPO]
        projetos = [p for p in self.servico.banco.listar_projetos() if nome in p.nome.lower()]
        tags = [g for g in self.servico.banco.listar_tags() if nome in g.nome.lower()]
        filtros = [f for f in self.servico.banco.listar_filtros() if nome in f.nome.lower()]
        if tarefas:
            self._cabecalho("Tarefas")
            for t in tarefas:
                rot = rotulo_prazo(t.prazo)[0].split(",")[0] if t.prazo else ""
                self._item(t.titulo, "concluido" if t.concluida_em else "circulo",
                           pal.apagado, "tarefa", t.id, rot)
        if projetos:
            self._cabecalho("Listas")
            for p in projetos[:MAX_POR_GRUPO]:
                self._item(p.nome, "lista", getattr(p, "cor", None) or pal.apagado, "lista", p.id)
        if tags:
            self._cabecalho("Etiquetas")
            for g in tags[:MAX_POR_GRUPO]:
                self._item(g.nome, "etiqueta", pal.apagado, "tag", g.nome)
        if filtros:
            self._cabecalho("Filtros")
            for f in filtros[:MAX_POR_GRUPO]:
                self._item(f.nome, "filtro", pal.apagado, "filtro", f.id)
        if tarefas:
            self._cabecalho("")
            self._item("Ver todos os resultados na lista", "busca", pal.destaque, "todos", texto)
        if self.lista.count() == 0:
            self.dica.setText("Nenhum resultado")
            self.pilha.setCurrentIndex(0)
            return
        self.dica.setText("Pesquisar tarefas, etiquetas, listas e filtros")
        self.pilha.setCurrentIndex(1)
        self._mover_para_primeiro()

    def _mover_para_primeiro(self):
        self.lista.setCurrentRow(-1)
        self._mover(1)

    # ---- ação ----
    def ativar(self, item: QListWidgetItem):
        tipo, valor = item.data(PAPEL_TIPO), item.data(PAPEL_VALOR)
        if tipo in (None, "cabecalho"):
            return
        texto = self.campo.text()
        self.close()
        j = self.janela
        if tipo == "tarefa":
            t = self.servico.banco.obter_tarefa(valor)
            if t is None:
                return
            j.mostrar_pagina("tarefas")
            j.selecionar_lista(_srv.CONCLUIDAS if t.concluida_em else (t.projeto_id or _srv.CAIXA))
            j.atualizar(selecionar_id=t.id)
            j.selecionar_tarefa(t.id)
        elif tipo == "lista":
            j.mostrar_pagina("tarefas")
            j.selecionar_lista(valor)
        elif tipo == "tag":
            j.mostrar_pagina("tarefas")
            j.selecionar_lista(_srv.chave_tag(valor))
        elif tipo == "filtro":
            j.mostrar_pagina("tarefas")
            j.selecionar_lista(_srv.chave_filtro(valor))
        elif tipo == "todos":
            j.btn_busca.setChecked(True)
            j.busca.setText(valor)
