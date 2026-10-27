"""Cartões de tarefa arrastáveis, usados no Kanban e na Matriz de Eisenhower."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QMimeData, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QStyle, QStyledItemDelegate

from ..core import Tarefa
from . import icones, tema
from .delegados import PAPEL_TAREFA
from .formatacao import rotulo_com_hora
from .util import com_alfa

MIME_TAREFA = "application/x-tarefa-id"
ALTURA_CARTAO = 74


def area_circulo(cartao: QRect) -> QRect:
    return QRect(cartao.left() + 14, cartao.top() + 14, 18, 18)


class DelegadoCartao(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.projetos: dict[int, object] = {}
        self.cores_tags: dict[str, str] = {}
        self.mostrar_projeto = False

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), ALTURA_CARTAO)

    def paint(self, p: QPainter, option, index):
        pal = tema.atual
        t: Tarefa = index.data(PAPEL_TAREFA)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = option.rect.adjusted(4, 3, -4, -3)
        selecionado = bool(option.state & QStyle.State_Selected)
        p.setPen(QPen(QColor(pal.destaque if selecionado else pal.borda), 1))
        p.setBrush(QColor(pal.linha_selecionada if selecionado else pal.campo))
        p.drawRoundedRect(QRectF(r), 8, 8)
        cor_prio = QColor(pal.prioridade[int(t.prioridade)])
        if t.prioridade:
            p.setPen(Qt.NoPen)
            p.setBrush(cor_prio)
            p.drawRoundedRect(QRectF(r.left(), r.top() + 8, 3, r.height() - 16), 1.5, 1.5)

        if not t.eh_nota:
            c = QRectF(area_circulo(r)).adjusted(1, 1, -1, -1)
            if t.concluida:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#5c5c5c"))
                p.drawEllipse(c)
                p.setPen(QPen(QColor("#ffffff"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                m = c.center()
                p.drawPolyline([QPointF(m.x() - 3.5, m.y() + 0.2), QPointF(m.x() - 1, m.y() + 2.8),
                                QPointF(m.x() + 3.5, m.y() - 2.6)])
            else:
                p.setPen(QPen(cor_prio, 1.6))
                p.setBrush(com_alfa(pal.prioridade[int(t.prioridade)], 46 if t.prioridade else 0))
                p.drawEllipse(c)
        else:
            icones.desenhar(p, "nota", QRectF(r.left() + 13, r.top() + 13, 19, 19), pal.apagado)

        fonte = QFont(option.font)
        fonte.setPixelSize(14)
        fonte.setStrikeOut(t.finalizada)
        p.setFont(fonte)
        fm = QFontMetrics(fonte)
        x0 = r.left() + 42
        largura = r.right() - x0 - 10
        p.setPen(QColor(pal.apagado if t.finalizada else pal.texto))
        p.drawText(QRect(x0, r.top() + 8, largura, 38), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                   fm.elidedText(t.titulo, Qt.ElideRight, largura * 2 - 10))

        # linha de baixo: data, etiquetas
        fonte2 = QFont(option.font)
        fonte2.setPixelSize(12)
        p.setFont(fonte2)
        fm2 = QFontMetrics(fonte2)
        x = x0
        y = QRect(0, r.bottom() - 24, 0, 18)
        if t.prazo:
            rot = rotulo_com_hora(t.prazo, t.prazo_hora)
            cor = pal.vermelho if t.atrasada else (pal.destaque if t.prazo == date.today() else pal.apagado)
            larg = fm2.horizontalAdvance(rot)
            p.setPen(QColor(cor))
            p.drawText(QRect(x, y.top(), larg, 18), Qt.AlignVCenter | Qt.AlignLeft, rot)
            x += larg + 10
        for nome in t.tags[:2]:
            texto = f"#{nome}"
            larg = fm2.horizontalAdvance(texto)
            if x + larg > r.right() - 8:
                break
            p.setPen(QColor(self.cores_tags.get(nome, pal.destaque)))
            p.drawText(QRect(x, y.top(), larg, 18), Qt.AlignVCenter | Qt.AlignLeft, texto)
            x += larg + 8
        if t.fixada:
            icones.desenhar(p, "fixar", QRectF(r.right() - 22, r.bottom() - 24, 14, 14), pal.destaque)
        p.restore()


class ListaCartoes(QListWidget):
    """Coluna de cartões: arrasta para outra coluna (a janela decide o que a soltura significa)."""

    soltou = Signal(int, object)        # id da tarefa, chave da coluna
    alternou = Signal(int)              # clicou no círculo de conclusão
    clicou_tarefa = Signal(int, object)  # clique (sem arrastar) no cartão: id e retângulo dele na tela

    def __init__(self, chave):
        super().__init__()
        self.chave = chave
        self.setObjectName("cartoes")
        self.setMouseTracking(True)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSpacing(0)
        self.delegado = DelegadoCartao(self)
        self.setItemDelegate(self.delegado)
        self.setStyleSheet("QListWidget#cartoes { background: transparent; border: none; }")
        self._toque = None

    def preencher(self, tarefas: list[Tarefa]) -> None:
        self.blockSignals(True)
        self.clear()
        for t in tarefas:
            item = QListWidgetItem()
            item.setData(PAPEL_TAREFA, t)
            self.addItem(item)
        self.blockSignals(False)

    def tarefa_do_item(self, item) -> Tarefa | None:
        return item.data(PAPEL_TAREFA) if item is not None else None

    def selecionar_id(self, tarefa_id: int | None) -> None:
        self.blockSignals(True)
        self.setCurrentItem(None)
        for i in range(self.count()):
            t = self.item(i).data(PAPEL_TAREFA)
            if t is not None and t.id == tarefa_id:
                self.setCurrentRow(i)
        self.blockSignals(False)

    # ---- clique no círculo ----
    def mousePressEvent(self, e):
        item = self.itemAt(e.position().toPoint())
        t = self.tarefa_do_item(item)
        if t is not None and e.button() == Qt.LeftButton and not t.eh_nota:
            cartao = self.visualItemRect(item).adjusted(4, 3, -4, -3)
            if area_circulo(cartao).adjusted(-5, -5, 5, 5).contains(e.position().toPoint()):
                self.alternou.emit(t.id)
                return
        self._toque = (t.id, e.position().toPoint()) if (t is not None and e.button() == Qt.LeftButton) else None
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.mousePressEvent(e)           # o 2º clique de um duplo clique conta como um clique normal

    def mouseReleaseEvent(self, e):
        toque, self._toque = self._toque, None
        super().mouseReleaseEvent(e)
        if toque is None or e.button() != Qt.LeftButton:
            return
        pos = e.position().toPoint()
        if (pos - toque[1]).manhattanLength() > 6:
            return
        item = self.itemAt(pos)
        t = self.tarefa_do_item(item)
        if t is not None and t.id == toque[0]:
            r = self.visualItemRect(item)
            self.clicou_tarefa.emit(t.id, QRect(self.viewport().mapToGlobal(r.topLeft()), r.size()))

    # ---- arrastar e soltar ----
    def startDrag(self, actions):
        t = self.tarefa_do_item(self.currentItem())
        if t is None:
            return
        mime = QMimeData()
        mime.setData(MIME_TAREFA, str(t.id).encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME_TAREFA):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(MIME_TAREFA):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        if not e.mimeData().hasFormat(MIME_TAREFA):
            e.ignore()
            return
        tarefa_id = int(bytes(e.mimeData().data(MIME_TAREFA)).decode())
        e.acceptProposedAction()
        self.soltou.emit(tarefa_id, self.chave)
