"""Ícones desenhados em código (traços simples, sem arquivos de imagem)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _caneta(cor, largura=1.6):
    return QPen(QColor(cor), largura, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)


def desenhar(p: QPainter, nome: str, r: QRectF, cor: str, texto: str = "") -> None:
    """Desenha o ícone `nome` dentro do retângulo `r`."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(Qt.NoBrush)
    p.setPen(_caneta(cor))
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    u = w / 20.0  # unidade: ícone numa grade 20x20

    def P(a, b):
        return QPointF(x + a * u, y + b * u)

    def R(a, b, c, d):
        return QRectF(x + a * u, y + b * u, c * u, d * u)

    if nome in ("hoje", "proximos", "calendario"):
        p.drawRoundedRect(R(2.5, 3.5, 15, 14), 3 * u, 3 * u)
        p.drawLine(P(2.5, 7.5), P(17.5, 7.5))
        p.drawLine(P(6.5, 2), P(6.5, 5))
        p.drawLine(P(13.5, 2), P(13.5, 5))
        if texto:
            f = QFont(p.font())
            f.setPixelSize(max(int(6.5 * u), 6))
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
            p.setPen(QColor(cor))
            p.drawText(R(2.5, 8, 15, 9.5), Qt.AlignCenter, texto)
    elif nome == "caixa":
        path = QPainterPath()
        path.moveTo(P(2.5, 11.5))
        path.lineTo(P(5, 4.5))
        path.lineTo(P(15, 4.5))
        path.lineTo(P(17.5, 11.5))
        path.lineTo(P(17.5, 15))
        path.quadTo(P(17.5, 17), P(15.5, 17))
        path.lineTo(P(4.5, 17))
        path.quadTo(P(2.5, 17), P(2.5, 15))
        path.closeSubpath()
        p.drawPath(path)
        path2 = QPainterPath()
        path2.moveTo(P(2.5, 11.5))
        path2.lineTo(P(7, 11.5))
        path2.quadTo(P(7.5, 14), P(10, 14))
        path2.quadTo(P(12.5, 14), P(13, 11.5))
        path2.lineTo(P(17.5, 11.5))
        p.drawPath(path2)
    elif nome == "lista":
        for yy in (5.5, 10, 14.5):
            p.drawLine(P(3.5, yy), P(16.5, yy))
    elif nome == "etiqueta":
        p.drawLine(P(8, 3.5), P(6.5, 16.5))
        p.drawLine(P(13.5, 3.5), P(12, 16.5))
        p.drawLine(P(3.5, 7.5), P(16.5, 7.5))
        p.drawLine(P(3, 12.5), P(16, 12.5))
    elif nome == "filtro":
        path = QPainterPath()
        path.moveTo(P(3, 4.5))
        path.lineTo(P(17, 4.5))
        path.lineTo(P(11.5, 11))
        path.lineTo(P(11.5, 16))
        path.lineTo(P(8.5, 14.5))
        path.lineTo(P(8.5, 11))
        path.closeSubpath()
        p.drawPath(path)
    elif nome == "concluido":
        p.drawRoundedRect(R(3, 3, 14, 14), 3 * u, 3 * u)
        p.drawPolyline([P(6.5, 10.2), P(9, 12.7), P(13.5, 7.5)])
    elif nome == "lixeira":
        p.drawLine(P(3.5, 5.5), P(16.5, 5.5))
        p.drawLine(P(8, 5.5), P(8, 3.5))
        p.drawLine(P(8, 3.5), P(12, 3.5))
        p.drawLine(P(12, 3.5), P(12, 5.5))
        path = QPainterPath()
        path.moveTo(P(5, 5.5))
        path.lineTo(P(5.8, 16))
        path.quadTo(P(6, 17), P(7, 17))
        path.lineTo(P(13, 17))
        path.quadTo(P(14, 17), P(14.2, 16))
        path.lineTo(P(15, 5.5))
        p.drawPath(path)
        p.drawLine(P(8.5, 8.5), P(8.5, 14))
        p.drawLine(P(11.5, 8.5), P(11.5, 14))
    elif nome == "tarefas":
        p.setBrush(QColor(cor))
        p.drawRoundedRect(R(3, 3, 14, 14), 3.5 * u, 3.5 * u)
        p.setBrush(Qt.NoBrush)
        p.setPen(_caneta("#181818", 2))
        p.drawPolyline([P(6.6, 10.3), P(9, 12.7), P(13.4, 7.6)])
    elif nome == "matriz":
        for a, b in ((3, 3), (11, 3), (3, 11), (11, 11)):
            p.drawRoundedRect(R(a, b, 6, 6), 1.8 * u, 1.8 * u)
    elif nome == "foco":
        p.drawEllipse(R(2.5, 2.5, 15, 15))
        p.drawEllipse(R(7, 7, 6, 6))
    elif nome == "habitos":
        p.drawEllipse(R(2.5, 2.5, 15, 15))
        p.drawLine(P(10, 6), P(10, 10))
        p.drawLine(P(10, 10), P(13, 12))
    elif nome == "busca":
        p.drawEllipse(R(3, 3, 11, 11))
        p.drawLine(P(12.5, 12.5), P(17, 17))
    elif nome == "repetir":
        p.drawArc(R(3.5, 3.5, 13, 13), 40 * 16, 140 * 16)
        p.drawArc(R(3.5, 3.5, 13, 13), 220 * 16, 140 * 16)
        p.drawLine(P(15.5, 3.5), P(16.4, 7.4))
        p.drawLine(P(16.4, 7.4), P(12.6, 7.2))
        p.drawLine(P(4.5, 16.5), P(3.6, 12.6))
        p.drawLine(P(3.6, 12.6), P(7.4, 12.8))
    elif nome == "ordenar":
        p.drawLine(P(6.5, 3.5), P(6.5, 16.5))
        p.drawPolyline([P(3.5, 6.5), P(6.5, 3.5), P(9.5, 6.5)])
        p.drawLine(P(13.5, 3.5), P(13.5, 16.5))
        p.drawPolyline([P(10.5, 13.5), P(13.5, 16.5), P(16.5, 13.5)])
    elif nome == "menu":
        for yy in (5.5, 10, 14.5):
            p.drawLine(P(3, yy), P(11 if yy != 10 else 14, yy))
    elif nome == "mais":
        p.drawLine(P(10, 4), P(10, 16))
        p.drawLine(P(4, 10), P(16, 10))
    elif nome == "sino":
        path = QPainterPath()
        path.moveTo(P(4.5, 14))
        path.quadTo(P(6, 12.5), P(6, 9))
        path.cubicTo(P(6, 4), P(14, 4), P(14, 9))
        path.quadTo(P(14, 12.5), P(15.5, 14))
        path.closeSubpath()
        p.drawPath(path)
        p.drawArc(R(8, 14, 4, 3.5), 200 * 16, 140 * 16)
    elif nome == "nota":
        p.drawRoundedRect(R(4, 3, 12, 14), 2.5 * u, 2.5 * u)
        p.drawLine(P(7, 8), P(13, 8))
        p.drawLine(P(7, 11.5), P(11, 11.5))
    elif nome == "todas":
        for yy in (5.5, 10, 14.5):
            p.drawLine(P(8, yy), P(16.5, yy))
            p.drawPoint(P(4, yy))
            p.drawEllipse(R(3, yy - 1, 2, 2))
    elif nome == "fixar":
        path = QPainterPath()
        path.moveTo(P(7, 3.5))
        path.lineTo(P(13, 3.5))
        path.lineTo(P(12, 9))
        path.lineTo(P(15, 11.5))
        path.lineTo(P(5, 11.5))
        path.lineTo(P(8, 9))
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(P(10, 11.5), P(10, 17))
    elif nome == "engrenagem":
        p.drawEllipse(R(7, 7, 6, 6))
        import math
        for k in range(8):
            ang = math.radians(k * 45)
            p.drawLine(P(10 + 5.2 * math.cos(ang), 10 + 5.2 * math.sin(ang)),
                       P(10 + 7.6 * math.cos(ang), 10 + 7.6 * math.sin(ang)))
        p.drawEllipse(R(4.8, 4.8, 10.4, 10.4))
    elif nome == "nao-sera-feito":
        p.drawRoundedRect(R(3, 3, 14, 14), 3.5 * u, 3.5 * u)
        p.drawLine(P(7, 7), P(13, 13))
        p.drawLine(P(13, 7), P(7, 13))
    elif nome == "contagem":
        path = QPainterPath()
        path.moveTo(P(5, 3.5))
        path.lineTo(P(15, 3.5))
        path.lineTo(P(10, 10))
        path.closeSubpath()
        path.moveTo(P(5, 16.5))
        path.lineTo(P(15, 16.5))
        path.lineTo(P(10, 10))
        path.closeSubpath()
        p.drawPath(path)
    elif nome == "estatisticas":
        p.drawLine(P(3, 16.5), P(17, 16.5))
        for a, altura in ((5, 6), (9.5, 10), (14, 7.5)):
            p.drawRoundedRect(R(a - 1.5, 16.5 - altura, 3, altura), 0.8 * u, 0.8 * u)
    elif nome == "ia":          # faísca grande e duas pequenas
        for cx, cy, r in ((9.5, 10.5, 6.5), (15.5, 4.5, 2.6), (15.5, 15.5, 2.2)):
            path = QPainterPath()
            path.moveTo(P(cx, cy - r))
            path.quadTo(P(cx, cy), P(cx + r, cy))
            path.quadTo(P(cx, cy), P(cx, cy + r))
            path.quadTo(P(cx, cy), P(cx - r, cy))
            path.quadTo(P(cx, cy), P(cx, cy - r))
            p.drawPath(path)
    elif nome == "clipe":        # clipe de papel, em pé
        path = QPainterPath()
        path.moveTo(P(6.5, 6.5))
        path.lineTo(P(6.5, 14))
        path.cubicTo(P(6.5, 18), P(13.5, 18), P(13.5, 14))
        path.lineTo(P(13.5, 5))
        path.cubicTo(P(13.5, 1.8), P(9.5, 1.8), P(9.5, 5))
        path.lineTo(P(9.5, 13.5))
        p.drawPath(path)
    elif nome == "microfone":
        p.drawRoundedRect(R(7.2, 2.5, 5.6, 9.5), 2.8 * u, 2.8 * u)
        arco = QPainterPath()
        arco.moveTo(P(4.5, 9.5))
        arco.cubicTo(P(4.5, 15.5), P(15.5, 15.5), P(15.5, 9.5))
        p.drawPath(arco)
        p.drawLine(P(10, 14.6), P(10, 17.5))
        p.drawLine(P(7, 17.5), P(13, 17.5))
    elif nome == "kanban":
        for a, altura in ((3, 12), (8.2, 8), (13.4, 10)):
            p.drawRoundedRect(R(a, 4, 3.8, altura), 1 * u, 1 * u)
    elif nome == "linha-tempo":
        p.drawRoundedRect(R(3, 4.5, 8, 3), 1.2 * u, 1.2 * u)
        p.drawRoundedRect(R(7, 9, 9, 3), 1.2 * u, 1.2 * u)
        p.drawRoundedRect(R(5, 13.5, 6, 3), 1.2 * u, 1.2 * u)
    elif nome == "clipe":
        path = QPainterPath()
        path.moveTo(P(14.5, 8))
        path.lineTo(P(9, 13.5))
        path.cubicTo(P(7.5, 15), P(5, 12.5), P(6.5, 11))
        path.lineTo(P(12, 5.5))
        path.cubicTo(P(13.5, 4), P(16, 6.5), P(14.5, 8))
        p.drawPath(path)
    elif nome == "comentario":
        p.drawRoundedRect(R(3, 4, 14, 10), 3 * u, 3 * u)
        p.drawPolyline([P(7, 14), P(7, 17), P(10.5, 14)])
    elif nome == "modelo":
        p.drawRoundedRect(R(3.5, 3.5, 13, 13), 2.5 * u, 2.5 * u)
        p.drawLine(P(3.5, 8), P(16.5, 8))
        p.drawLine(P(8, 8), P(8, 16.5))
    elif nome == "play":
        path = QPainterPath()
        path.moveTo(P(6.5, 4))
        path.lineTo(P(16, 10))
        path.lineTo(P(6.5, 16))
        path.closeSubpath()
        p.setBrush(QColor(cor))
        p.drawPath(path)
    elif nome == "calendario-mais":
        p.drawRoundedRect(R(2.5, 3.5, 15, 14), 3 * u, 3 * u)
        p.drawLine(P(2.5, 7.5), P(17.5, 7.5))
        p.drawLine(P(10, 10), P(10, 15))
        p.drawLine(P(7.5, 12.5), P(12.5, 12.5))
    elif nome == "bandeira":
        p.drawLine(P(5, 3.5), P(5, 17))
        path = QPainterPath()
        path.moveTo(P(5, 4))
        path.lineTo(P(15, 4))
        path.lineTo(P(12.5, 7.5))
        path.lineTo(P(15, 11))
        path.lineTo(P(5, 11))
        p.drawPath(path)
    elif nome == "bandeira-cheia":
        p.drawLine(P(5, 3.5), P(5, 17))
        path = QPainterPath()
        path.moveTo(P(5, 4))
        path.lineTo(P(15, 4))
        path.lineTo(P(12.5, 7.5))
        path.lineTo(P(15, 11))
        path.lineTo(P(5, 11))
        p.setBrush(QColor(cor))
        p.drawPath(path)
    elif nome == "sol":
        p.drawEllipse(R(6.5, 6.5, 7, 7))
        for ang in range(0, 360, 45):
            import math
            a = math.radians(ang)
            p.drawLine(P(10 + 6.2 * math.cos(a), 10 + 6.2 * math.sin(a)), P(10 + 8.2 * math.cos(a), 10 + 8.2 * math.sin(a)))
    elif nome == "nascer-do-sol":
        p.drawArc(R(5.5, 8, 9, 9), 0, 180 * 16)
        p.drawLine(P(3, 14.5), P(17, 14.5))
        for ang in (-60, -90, -120):
            import math
            a = math.radians(ang)
            p.drawLine(P(10 + 6 * math.cos(a), 14.5 + 6 * math.sin(a)), P(10 + 8 * math.cos(a), 14.5 + 8 * math.sin(a)))
    elif nome == "lua":
        path = QPainterPath()
        path.moveTo(P(13.5, 3.5))
        path.cubicTo(P(8, 4), P(5, 9), P(7, 13.5))
        path.cubicTo(P(9, 17.5), P(14.5, 17.5), P(17, 13.5))
        path.cubicTo(P(12, 14), P(10.5, 8), P(13.5, 3.5))
        p.drawPath(path)
    elif nome == "relogio":
        p.drawEllipse(R(3, 3, 14, 14))
        p.drawPolyline([P(10, 6), P(10, 10), P(13, 11.5)])
    elif nome == "reticencias":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(cor))
        for xx in (4.5, 10, 15.5):
            p.drawEllipse(P(xx, 10), 1.4 * u, 1.4 * u)
    elif nome == "seta-dir":
        p.drawPolyline([P(7.5, 5), P(12.5, 10), P(7.5, 15)])
    elif nome == "seta-esq":
        p.drawPolyline([P(12.5, 5), P(7.5, 10), P(12.5, 15)])
    elif nome == "seta-baixo":
        p.drawPolyline([P(5, 7.5), P(10, 12.5), P(15, 7.5)])
    elif nome == "fechar":
        p.drawLine(P(5, 5), P(15, 15))
        p.drawLine(P(15, 5), P(5, 15))
    elif nome == "circulo":
        p.drawEllipse(R(4, 4, 12, 12))
    elif nome == "aberto":
        p.drawRoundedRect(R(4, 4, 12, 12), 3 * u, 3 * u)
    elif nome == "avatar":
        p.drawEllipse(R(7, 3.5, 6, 6))
        p.drawArc(R(3.5, 11, 13, 10), 0, 180 * 16)
    p.restore()


def icone(nome: str, cor: str, tamanho: int = 20, texto: str = "") -> QIcon:
    return QIcon(pixmap(nome, cor, tamanho, texto))


def pixmap(nome: str, cor: str, tamanho: int = 20, texto: str = "") -> QPixmap:
    escala = 2  # nitidez em telas comuns
    pm = QPixmap(tamanho * escala, tamanho * escala)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    desenhar(p, nome, QRectF(0, 0, tamanho * escala, tamanho * escala), cor, texto)
    p.end()
    pm.setDevicePixelRatio(escala)
    return pm
