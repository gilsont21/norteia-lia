"""Desenho das linhas da barra lateral e da lista de tarefas."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from ..core import Tarefa
from . import icones, tema
from .formatacao import rotulo_com_hora

PAPEL_TAREFA = Qt.UserRole
PAPEL_TIPO = Qt.UserRole + 1      # "cabecalho" | "lista" | "projeto" | "etiqueta" | "dica" | "divisor"
PAPEL_CHAVE = Qt.UserRole + 2
PAPEL_CONTAGEM = Qt.UserRole + 3
PAPEL_COR = Qt.UserRole + 4
PAPEL_ICONE = Qt.UserRole + 5
PAPEL_ROTULO_ICONE = Qt.UserRole + 6   # texto dentro do ícone (ex.: dia do mês)
PAPEL_EMOJI = Qt.UserRole + 7          # emoji da lista (aparece no lugar do ícone)
COR_SEM_COR = "#8a8f98"


def area_caixa(linha: QRect) -> QRect:
    """Área clicável do quadradinho de conclusão."""
    return QRect(linha.left() + 16, linha.center().y() - 9, 18, 18)


class DelegadoTarefa(QStyledItemDelegate):
    ALTURA = 50
    ALTURA_GRUPO = 36

    def __init__(self, parent=None):
        super().__init__(parent)
        self.projetos: dict[int, object] = {}
        self.mostrar_projeto = True
        self.progressos: dict[int, tuple[int, int]] = {}
        self.cores_tags: dict[str, str] = {}      # só as etiquetas com cor escolhida

    def sizeHint(self, option, index):
        if index.data(PAPEL_TIPO) == "grupo":
            return QSize(option.rect.width(), self.ALTURA_GRUPO)
        return QSize(option.rect.width(), self.ALTURA)

    def _pintar_grupo(self, p: QPainter, option, index):
        pal = tema.atual
        p.save()
        r = option.rect
        fonte = QFont(option.font)
        fonte.setPixelSize(13)
        fonte.setWeight(QFont.DemiBold)
        p.setFont(fonte)
        p.setPen(QColor(pal.apagado))
        texto = index.data(Qt.DisplayRole)
        p.drawText(QRect(r.left() + 16, r.top() + 8, r.width() - 80, r.height() - 8),
                   Qt.AlignVCenter | Qt.AlignLeft, texto)
        n = index.data(PAPEL_CONTAGEM)
        if n:
            p.drawText(QRect(r.right() - 64, r.top() + 8, 50, r.height() - 8),
                       Qt.AlignVCenter | Qt.AlignRight, str(n))
        p.restore()

    def paint(self, p: QPainter, option, index):
        if index.data(PAPEL_TIPO) == "grupo":
            self._pintar_grupo(p, option, index)
            return
        pal = tema.atual
        t: Tarefa = index.data(PAPEL_TAREFA)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = option.rect

        if option.state & QStyle.State_Selected:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal.linha_selecionada))
            p.drawRoundedRect(r.adjusted(4, 1, -4, -1), 6, 6)
        elif option.state & QStyle.State_MouseOver:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal.linha_hover))
            p.drawRoundedRect(r.adjusted(4, 1, -4, -1), 6, 6)
        else:  # separador fino embaixo
            p.setPen(QPen(QColor(pal.borda), 1))
            p.drawLine(r.left() + 16, r.bottom(), r.right() - 8, r.bottom())

        # quadradinho de conclusão
        caixa = area_caixa(r)
        quad = QRectF(caixa).adjusted(1, 1, -1, -1)
        cor_prio = QColor(pal.prioridade[int(t.prioridade)])
        if t.descartada and not t.concluida:
            p.setPen(QPen(QColor("#5c5c5c"), 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(quad, 4, 4)
            c = quad.center()
            p.drawLine(QPointF(c.x() - 3.5, c.y() - 3.5), QPointF(c.x() + 3.5, c.y() + 3.5))
            p.drawLine(QPointF(c.x() + 3.5, c.y() - 3.5), QPointF(c.x() - 3.5, c.y() + 3.5))
        elif t.concluida:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#5c5c5c"))
            p.drawRoundedRect(quad, 4, 4)
            p.setPen(QPen(QColor("#ffffff"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            c = quad.center()
            p.drawPolyline([QPointF(c.x() - 4, c.y() + 0.2), QPointF(c.x() - 1.2, c.y() + 3),
                            QPointF(c.x() + 4, c.y() - 3)])
        else:
            tint = QColor(cor_prio)
            tint.setAlpha(46 if t.prioridade else 0)
            p.setBrush(tint)
            p.setPen(QPen(cor_prio, 1.6))
            p.drawRoundedRect(quad, 4, 4)

        # direita: projeto, repetição, data
        fonte_d = QFont(option.font)
        fonte_d.setPixelSize(13)
        p.setFont(fonte_d)
        fmd = QFontMetrics(fonte_d)
        x_dir = r.right() - 14
        reservado = 0
        if t.fixada:
            icones.desenhar(p, "fixar", QRectF(x_dir - 15, r.center().y() - 7, 15, 15), pal.destaque)
            x_dir -= 24
            reservado += 24
        if t.prazo:
            rot = rotulo_com_hora(t.prazo, t.prazo_hora)
            if t.atrasada:
                cor = pal.vermelho
            elif t.prazo == date.today():
                cor = pal.destaque
            else:
                cor = pal.apagado
            larg = fmd.horizontalAdvance(rot)
            p.setPen(QColor(cor))
            p.drawText(QRect(x_dir - larg, r.top(), larg, r.height()), Qt.AlignVCenter | Qt.AlignRight, rot)
            x_dir -= larg + 8
            reservado += larg + 8
            if t.repeticao:
                icones.desenhar(p, "repetir", QRectF(x_dir - 14, r.center().y() - 7, 14, 14), cor)
                x_dir -= 22
                reservado += 22
        if self.mostrar_projeto and t.projeto_id and t.projeto_id in self.projetos:
            nome = self.projetos[t.projeto_id].nome
            nome = fmd.elidedText(nome, Qt.ElideRight, 120)
            larg = fmd.horizontalAdvance(nome)
            p.setPen(QColor(pal.apagado))
            p.drawText(QRect(x_dir - larg, r.top(), larg, r.height()), Qt.AlignVCenter | Qt.AlignRight, nome)
            x_dir -= larg + 16
            reservado += larg + 16
        prog = self.progressos.get(t.id)
        if prog:
            texto_prog = f"{prog[0]}/{prog[1]}"
            larg = fmd.horizontalAdvance(texto_prog)
            p.setPen(QColor(pal.apagado))
            p.drawText(QRect(x_dir - larg, r.top(), larg, r.height()), Qt.AlignVCenter | Qt.AlignRight, texto_prog)
            reservado += larg + 16

        # título e etiquetas
        x0 = r.left() + 48
        fonte = QFont(option.font)
        fonte.setPixelSize(15)
        fonte.setStrikeOut(t.finalizada)
        p.setFont(fonte)
        fm = QFontMetrics(fonte)
        maximo = r.right() - x0 - reservado - 20
        titulo = fm.elidedText(t.titulo, Qt.ElideRight, max(maximo, 40))
        p.setPen(QColor(pal.apagado if t.finalizada else pal.texto))
        p.drawText(QRect(x0, r.top(), maximo, r.height()), Qt.AlignVCenter | Qt.AlignLeft, titulo)
        x = x0 + fm.horizontalAdvance(titulo) + 10
        fonte_t = QFont(option.font)
        fonte_t.setPixelSize(13)
        p.setFont(fonte_t)
        fmt = QFontMetrics(fonte_t)
        limite = x0 + maximo
        for nome in t.tags[:3]:
            texto = f"#{nome}"
            larg = fmt.horizontalAdvance(texto)
            if x + larg > limite:
                break
            p.setPen(QColor(self.cores_tags.get(nome, pal.destaque)))
            p.drawText(QRect(x, r.top(), larg, r.height()), Qt.AlignVCenter | Qt.AlignLeft, texto)
            x += larg + 10
        p.restore()


class DelegadoBarra(QStyledItemDelegate):
    @staticmethod
    def rect_mais(r: QRect) -> QRect:
        """Área do botão "+" nos cabeçalhos Listas, Etiquetas e Filtros (lado direito)."""
        return QRect(r.right() - 44, r.top() + 8, 32, 28)

    def sizeHint(self, option, index):
        tipo = index.data(PAPEL_TIPO)
        w = option.rect.width()
        if tipo == "cabecalho":
            return QSize(w, 40)
        if tipo == "divisor":
            return QSize(w, 18)
        if tipo == "dica":
            fonte = QFont(option.font)
            fonte.setPixelSize(13)
            caixa = QFontMetrics(fonte).boundingRect(
                0, 0, max(w - 48, 80), 1000, Qt.TextWordWrap, index.data(Qt.DisplayRole))
            return QSize(w, caixa.height() + 30)
        return QSize(w, 40)

    def paint(self, p: QPainter, option, index):
        pal = tema.atual
        tipo = index.data(PAPEL_TIPO)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = option.rect
        fonte = QFont(option.font)

        if tipo == "divisor":
            p.setPen(QPen(QColor(pal.borda), 1))
            p.drawLine(r.left() + 14, r.center().y(), r.right() - 14, r.center().y())
            p.restore()
            return
        if tipo == "cabecalho":
            fonte.setPixelSize(13)
            fonte.setWeight(QFont.DemiBold)
            p.setFont(fonte)
            p.setPen(QColor(pal.apagado))
            p.drawText(QRect(r.left() + 18, r.top() + 10, r.width() - 36, 24),
                       Qt.AlignVCenter | Qt.AlignLeft, index.data(Qt.DisplayRole))
            if str(index.data(PAPEL_CHAVE) or "").startswith("novo:"):
                alvo = self.rect_mais(r)
                if option.state & QStyle.State_MouseOver:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(pal.barra_ativa))
                    p.drawRoundedRect(alvo.adjusted(2, 2, -2, -2), 6, 6)
                    icones.desenhar(p, "mais", QRectF(alvo.center().x() - 8, alvo.center().y() - 8, 16, 16),
                                    pal.texto_barra, "")
            p.restore()
            return
        if tipo == "dica":
            fonte.setPixelSize(13)
            p.setFont(fonte)
            caixa = r.adjusted(8, 2, -8, -6)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal.campo))
            p.drawRoundedRect(caixa, 6, 6)
            p.setPen(QColor(pal.apagado))
            p.drawText(caixa.adjusted(10, 8, -10, -8), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop,
                       index.data(Qt.DisplayRole))
            p.restore()
            return

        ativo = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        caixa = r.adjusted(8, 2, -8, -2)
        if ativo or hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal.barra_ativa if ativo else pal.barra_hover))
            p.drawRoundedRect(caixa, 7, 7)

        emoji = index.data(PAPEL_EMOJI)
        nome_icone = index.data(PAPEL_ICONE) or ("lista" if tipo == "projeto" else "etiqueta")
        cor_icone = index.data(PAPEL_COR) if tipo == "etiqueta" and index.data(PAPEL_COR) else pal.texto_barra
        if tipo == "arquivada":
            cor_icone = pal.apagado
        if emoji:
            fe = QFont(option.font)
            fe.setPixelSize(16)
            p.setFont(fe)
            p.setPen(QColor(pal.texto_barra))
            p.drawText(QRectF(caixa.left() + 8, caixa.center().y() - 12, 24, 24), Qt.AlignCenter, emoji)
        else:
            icones.desenhar(p, nome_icone, QRectF(caixa.left() + 10, caixa.center().y() - 10, 20, 20),
                            cor_icone, index.data(PAPEL_ROTULO_ICONE) or "")
        fonte.setPixelSize(15)
        p.setFont(fonte)
        p.setPen(QColor(pal.texto_barra))
        fm = QFontMetrics(fonte)
        tem_extra = bool(index.data(PAPEL_CONTAGEM)) or (
            tipo == "projeto" and index.data(PAPEL_COR) and index.data(PAPEL_COR) != COR_SEM_COR)
        texto = fm.elidedText(index.data(Qt.DisplayRole), Qt.ElideRight,
                              caixa.width() - (120 if tem_extra else 60))
        p.drawText(QRect(caixa.left() + 42, caixa.top(), caixa.width() - 100, caixa.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, texto)

        n = index.data(PAPEL_CONTAGEM)
        x_fim = caixa.right() - 10
        if n:
            fonte.setPixelSize(13)
            p.setFont(fonte)
            p.setPen(QColor(pal.apagado))
            p.drawText(QRect(x_fim - 40, caixa.top(), 40, caixa.height()),
                       Qt.AlignVCenter | Qt.AlignRight, str(n))
        cor = index.data(PAPEL_COR)
        if tipo == "projeto" and cor and cor != COR_SEM_COR:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(cor))
            p.drawEllipse(QPointF(x_fim - 54, caixa.center().y() + 0.5), 4, 4)
        p.restore()
