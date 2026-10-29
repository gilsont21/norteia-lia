"""Fundos ilustrados das estações do ano, desenhados em código (sem arquivos de imagem).

`pintar` desenha uma cena dentro de um retângulo. O fundo da área central usa a parte de baixo da cena,
com transparência, para não atrapalhar a leitura. As miniaturas da tela de Aparência usam a cena inteira.
"""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QStyle, QStyleOption, QWidget

ESTACOES = [("primavera", "Primavera"), ("verao", "Verão"), ("outono", "Outono"), ("inverno", "Inverno")]
NOME = dict(ESTACOES)

# cada estação: cores para o modo claro e para o modo escuro
CORES = {
    "primavera": {
        False: dict(ceu=("#d9f2e3", "#f4fbe9"), astro="#ffe48a", c1="#bde6a8", c2="#93d48c", c3="#74c47e",
                    copa="#f6b9d0", copa2="#f08fb1", tronco="#8b6b52", detalhe="#ffffff", nuvem="#ffffff"),
        True: dict(ceu=("#14231b", "#1c2d22"), astro="#d9c97f", c1="#2c4a34", c2="#244029", c3="#1d3622",
                   copa="#8b5368", copa2="#a8607b", tronco="#5b4636", detalhe="#c9d8c0", nuvem="#2a3f31"),
    },
    "verao": {
        False: dict(ceu=("#b9e9ff", "#e9f8ff"), astro="#ffd54a", c1="#f6e3ab", c2="#46c2dc", c3="#2aa5c8",
                    c4="#1a8db4", barco="#ffffff", casco="#e0654f", nuvem="#ffffff"),
        True: dict(ceu=("#0e2133", "#16344b"), astro="#d8b24a", c1="#4a4332", c2="#1f6e86", c3="#18596f",
                   c4="#10475b", barco="#c9d4dc", casco="#9a4a3d", nuvem="#243d52"),
    },
    "outono": {
        False: dict(ceu=("#ffe2cc", "#fff3e6"), astro="#ffb36b", c1="#f4b67c", c2="#e48d4c", c3="#cc7038",
                    copa="#e8803a", copa2="#c9482b", copa3="#f2b134", tronco="#7a4a2e", nuvem="#fff6ee"),
        True: dict(ceu=("#2a1b14", "#35241a"), astro="#c98a4e", c1="#5a3a28", c2="#4b3022", c3="#3d271c",
                   copa="#a8582a", copa2="#8a3520", copa3="#b88a2a", tronco="#4a3123", nuvem="#4a3326"),
    },
    "inverno": {
        False: dict(ceu=("#d8e7fb", "#f4f8ff"), astro="#fff7d0", c1="#ffffff", c2="#e3edfb", c3="#cfdff5",
                    pinheiro="#5a8f78", neve="#ffffff", tronco="#7a5b45", nuvem="#ffffff"),
        True: dict(ceu=("#121a2a", "#1a2438"), astro="#e8e4c8", c1="#3b4860", c2="#2f3b52", c3="#27324a",
                   pinheiro="#2f5a4a", neve="#c9d6ea", tronco="#4a3a2e", nuvem="#26324a"),
    },
}


def _c(hexa: str, alfa: float = 1.0) -> QColor:
    c = QColor(hexa)
    c.setAlphaF(alfa)
    return c


def _colina(p: QPainter, r: QRectF, base: float, amp: float, fase: float, freq: float, cor: str) -> None:
    caminho = QPainterPath()
    caminho.moveTo(r.left(), r.bottom())
    passos = 48
    for i in range(passos + 1):
        t = i / passos
        y = r.top() + r.height() * (base + amp * math.sin(t * math.pi * 2 * freq + fase))
        caminho.lineTo(r.left() + r.width() * t, y)
    caminho.lineTo(r.right(), r.bottom())
    caminho.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(_c(cor))
    p.drawPath(caminho)


def _y_da_colina(r: QRectF, base: float, amp: float, fase: float, freq: float, t: float) -> float:
    return r.top() + r.height() * (base + amp * math.sin(t * math.pi * 2 * freq + fase))


def _nuvem(p: QPainter, cx: float, cy: float, u: float, cor: str) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(_c(cor))
    p.drawEllipse(QPointF(cx, cy), u * 1.0, u * 0.55)
    p.drawEllipse(QPointF(cx - u * 0.8, cy + u * 0.12), u * 0.65, u * 0.4)
    p.drawEllipse(QPointF(cx + u * 0.85, cy + u * 0.1), u * 0.7, u * 0.42)


def _arvore(p: QPainter, cx: float, base: float, h: float, tronco: str, copas: list[str]) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(_c(tronco))
    p.drawRoundedRect(QRectF(cx - h * 0.04, base - h * 0.45, h * 0.08, h * 0.45), h * 0.02, h * 0.02)
    p.setBrush(_c(copas[0]))
    p.drawEllipse(QPointF(cx, base - h * 0.62), h * 0.30, h * 0.28)
    p.setBrush(_c(copas[1 % len(copas)]))
    p.drawEllipse(QPointF(cx - h * 0.17, base - h * 0.52), h * 0.20, h * 0.18)
    p.setBrush(_c(copas[2 % len(copas)]))
    p.drawEllipse(QPointF(cx + h * 0.18, base - h * 0.55), h * 0.19, h * 0.17)


def _pinheiro(p: QPainter, cx: float, base: float, h: float, cor: str, neve: str, tronco: str) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(_c(tronco))
    p.drawRect(QRectF(cx - h * 0.04, base - h * 0.16, h * 0.08, h * 0.16))
    for i in range(3):
        topo = base - h * (0.95 - i * 0.26)
        larg = h * (0.22 + i * 0.12)
        corpo = QPainterPath()
        corpo.moveTo(cx, topo)
        corpo.lineTo(cx - larg, topo + h * 0.42)
        corpo.lineTo(cx + larg, topo + h * 0.42)
        corpo.closeSubpath()
        p.setBrush(_c(cor))
        p.drawPath(corpo)
        capa = QPainterPath()
        capa.moveTo(cx, topo)
        capa.lineTo(cx - larg * 0.48, topo + h * 0.20)
        capa.quadTo(cx, topo + h * 0.27, cx + larg * 0.48, topo + h * 0.20)
        capa.closeSubpath()
        p.setBrush(_c(neve))
        p.drawPath(capa)


def pintar(p: QPainter, r: QRectF, estacao: str, escuro: bool, com_ceu: bool = True) -> None:
    """Desenha a cena `estacao` ocupando `r`. Sem céu, só a paisagem (para usar como fundo transparente)."""
    if estacao not in CORES:
        return
    k = CORES[estacao][bool(escuro)]
    rng = random.Random(estacao)            # mesma cena sempre
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setClipRect(r)
    if com_ceu:
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, _c(k["ceu"][0]))
        g.setColorAt(1, _c(k["ceu"][1]))
        p.fillRect(r, QBrush(g))
    u = r.height() / 100.0

    def X(t):
        return r.left() + r.width() * t

    def Y(t):
        return r.top() + r.height() * t

    # céu: astro, nuvens e estrelas
    if com_ceu:
        if escuro:
            for _ in range(28):
                p.setPen(Qt.NoPen)
                p.setBrush(_c("#ffffff", rng.uniform(0.25, 0.7)))
                p.drawEllipse(QPointF(X(rng.random()), Y(rng.uniform(0.02, 0.45))), u * 0.35, u * 0.35)
        p.setPen(Qt.NoPen)
        p.setBrush(_c(k["astro"], 0.35))
        p.drawEllipse(QPointF(X(0.80), Y(0.24)), u * 15, u * 15)
        p.setBrush(_c(k["astro"]))
        p.drawEllipse(QPointF(X(0.80), Y(0.24)), u * 10, u * 10)
        _nuvem(p, X(0.22), Y(0.2), u * 7, k["nuvem"])
        _nuvem(p, X(0.55), Y(0.32), u * 5, k["nuvem"])

    if estacao == "primavera":
        _colina(p, r, 0.62, 0.05, 0.4, 1.1, k["c1"])
        _colina(p, r, 0.74, 0.05, 2.0, 1.3, k["c2"])
        _arvore(p, X(0.22), Y(0.78), u * 46, k["tronco"], [k["copa"], k["copa2"], k["copa"]])
        _arvore(p, X(0.72), Y(0.74), u * 34, k["tronco"], [k["copa2"], k["copa"], k["copa2"]])
        _colina(p, r, 0.88, 0.035, 0.8, 1.6, k["c3"])
        for _ in range(26):                                        # flores no gramado
            t = rng.random()
            y = Y(rng.uniform(0.86, 0.98))
            p.setBrush(_c(k["detalhe"] if rng.random() < 0.5 else k["copa2"]))
            p.drawEllipse(QPointF(X(t), y), u * 0.9, u * 0.9)
    elif estacao == "verao":
        _colina(p, r, 0.60, 0.0, 0.0, 1.0, k["c2"])               # mar ao fundo (faixa reta)
        for i, nome in enumerate(("c2", "c3", "c4")):
            caminho = QPainterPath()
            base = 0.60 + i * 0.12
            caminho.moveTo(r.left(), r.bottom())
            for j in range(61):
                t = j / 60
                caminho.lineTo(X(t), Y(base + 0.018 * math.sin(t * math.pi * (6 + i * 2) + i)))
            caminho.lineTo(r.right(), r.bottom())
            caminho.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(_c(k[nome]))
            p.drawPath(caminho)
        # barquinho
        p.setBrush(_c(k["casco"]))
        casco = QPainterPath()
        casco.moveTo(X(0.30), Y(0.62))
        casco.lineTo(X(0.45), Y(0.62))
        casco.lineTo(X(0.42), Y(0.68))
        casco.lineTo(X(0.33), Y(0.68))
        casco.closeSubpath()
        p.drawPath(casco)
        p.setBrush(_c(k["barco"]))
        vela = QPainterPath()
        vela.moveTo(X(0.375), Y(0.34))
        vela.lineTo(X(0.375), Y(0.60))
        vela.lineTo(X(0.44), Y(0.60))
        vela.closeSubpath()
        p.drawPath(vela)
        vela2 = QPainterPath()
        vela2.moveTo(X(0.36), Y(0.40))
        vela2.lineTo(X(0.36), Y(0.60))
        vela2.lineTo(X(0.31), Y(0.60))
        vela2.closeSubpath()
        p.drawPath(vela2)
        _colina(p, r, 0.93, 0.03, 0.5, 1.2, k["c1"])             # faixa de areia
    elif estacao == "outono":
        _colina(p, r, 0.60, 0.06, 1.0, 1.0, k["c1"])
        _colina(p, r, 0.73, 0.05, 2.6, 1.2, k["c2"])
        _arvore(p, X(0.18), Y(0.80), u * 50, k["tronco"], [k["copa"], k["copa2"], k["copa3"]])
        _arvore(p, X(0.60), Y(0.76), u * 38, k["tronco"], [k["copa3"], k["copa"], k["copa2"]])
        _arvore(p, X(0.86), Y(0.78), u * 44, k["tronco"], [k["copa2"], k["copa3"], k["copa"]])
        _colina(p, r, 0.90, 0.03, 0.2, 1.5, k["c3"])
        for _ in range(22):                                        # folhas caindo
            p.setPen(Qt.NoPen)
            p.setBrush(_c([k["copa"], k["copa2"], k["copa3"]][rng.randrange(3)], 0.9))
            p.save()
            p.translate(X(rng.random()), Y(rng.uniform(0.1, 0.95)))
            p.rotate(rng.uniform(0, 180))
            p.drawEllipse(QPointF(0, 0), u * 1.5, u * 0.8)
            p.restore()
    else:  # inverno
        _colina(p, r, 0.60, 0.05, 0.6, 1.0, k["c1"])
        _colina(p, r, 0.72, 0.05, 2.2, 1.2, k["c2"])
        for t, h in ((0.16, 42), (0.26, 30), (0.70, 38), (0.82, 48), (0.90, 28)):
            ys = _y_da_colina(r, 0.72, 0.05, 2.2, 1.2, t) + u * 3
            _pinheiro(p, X(t), ys, u * h, k["pinheiro"], k["neve"], k["tronco"])
        _colina(p, r, 0.88, 0.035, 0.4, 1.5, k["c3"])
        for _ in range(60):                                        # flocos
            p.setPen(Qt.NoPen)
            p.setBrush(_c("#ffffff" if not escuro else "#dbe6f7", rng.uniform(0.5, 0.95)))
            p.drawEllipse(QPointF(X(rng.random()), Y(rng.random())), u * rng.uniform(0.35, 0.9), u * rng.uniform(0.35, 0.9))
    p.restore()


class ComFundo(QWidget):
    """Widget que pinta o próprio fundo (do estilo) e, por cima, a cena da estação escolhida."""

    ALTURA_MAXIMA = 340
    OPACIDADE_CLARO = 0.34
    OPACIDADE_ESCURO = 0.38

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.estacao = ""
        self.escuro = True
        self._cache = None
        self.setAttribute(Qt.WA_StyledBackground, True)

    def definir_estacao(self, estacao: str, escuro: bool) -> None:
        self.estacao = estacao if estacao in CORES else ""
        self.escuro = escuro
        self.update()

    def _cena_pronta(self, largura: int, altura: int) -> QPixmap:
        chave = (self.estacao, self.escuro, largura, altura)
        if self._cache is not None and self._cache[0] == chave:
            return self._cache[1]
        pm = QPixmap(largura, altura)
        pm.fill(Qt.transparent)
        q = QPainter(pm)
        pintar(q, QRectF(0, 0, largura, altura), self.estacao, self.escuro, com_ceu=False)
        q.setCompositionMode(QPainter.CompositionMode_DestinationIn)   # some suavemente no alto, sem corte seco
        g = QLinearGradient(0, 0, 0, altura)
        g.setColorAt(0.0, QColor(0, 0, 0, 0))
        g.setColorAt(0.38, QColor(0, 0, 0, 255))
        g.setColorAt(1.0, QColor(0, 0, 0, 255))
        q.fillRect(0, 0, largura, altura, QBrush(g))
        q.end()
        self._cache = (chave, pm)
        return pm

    def paintEvent(self, e):
        p = QPainter(self)
        opt = QStyleOption()
        opt.initFrom(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, p, self)
        if self.estacao and self.width() > 40 and self.height() > 40:
            altura = int(min(self.height() * 0.46, self.ALTURA_MAXIMA))
            p.setOpacity(self.OPACIDADE_ESCURO if self.escuro else self.OPACIDADE_CLARO)
            p.drawPixmap(0, self.height() - altura, self._cena_pronta(self.width(), altura))
        p.end()
