"""Telas de Contagem regressiva e de Estatísticas."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QScrollArea, QToolTip, QVBoxLayout, QWidget)

from ..core.foco import formatar_duracao
from . import tema
from .dialogos import DialogoContagem
from .util import com_alfa, texto_sobre


def _rolagem(miolo: QWidget) -> QScrollArea:
    r = QScrollArea()
    r.setWidgetResizable(True)
    r.setFrameShape(QScrollArea.NoFrame)
    r.setStyleSheet("QScrollArea { background: transparent; }")
    miolo.setStyleSheet(miolo.styleSheet() + "background: transparent;")
    r.setWidget(miolo)
    return r


# ============================================================ Contagem regressiva
class CartaoContagem(QFrame):
    def __init__(self, pagina: "PaginaContagem", c, hoje: date):
        super().__init__()
        pal = tema.atual
        self.c = c
        self.setObjectName("cartaoContagem")
        self.setStyleSheet(f"QFrame#cartaoContagem {{ background: {pal.barra}; border-radius: 10px; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 12, 12)
        n = c.dias(hoje)
        num = QLabel(str(abs(n)) if n != 0 else "0")
        num.setFixedWidth(90)
        num.setAlignment(Qt.AlignCenter)
        passou = n < 0
        cor = pal.apagado if passou else c.cor
        num.setStyleSheet(f"font-size: 34px; font-weight: 700; color: {cor}; background: transparent;")
        lay.addWidget(num)
        col = QVBoxLayout()
        col.setSpacing(2)
        nome = QLabel(c.nome)
        nome.setStyleSheet("font-size: 15px; font-weight: 600; background: transparent;")
        quando = c.proxima_data(hoje)
        sub = QLabel(f"{c.texto(hoje)} · {quando:%d/%m/%Y}" + (" · todo ano" if c.anual else ""))
        sub.setStyleSheet(f"color: {pal.apagado}; background: transparent;")
        col.addWidget(nome)
        col.addWidget(sub)
        lay.addLayout(col, 1)
        ed, ap = QPushButton("Editar"), QPushButton("Apagar")
        ap.setObjectName("perigo")
        for b in (ed, ap):
            b.setCursor(Qt.PointingHandCursor)
            lay.addWidget(b)
        ed.clicked.connect(lambda: pagina.editar(c))
        ap.clicked.connect(lambda: pagina.apagar(c))


class PaginaContagem(QWidget):
    def __init__(self, janela):
        super().__init__()
        self.janela = janela
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 12)
        lay.setSpacing(10)
        cab = QHBoxLayout()
        titulo = QLabel("Contagem regressiva")
        titulo.setObjectName("titulo")
        cab.addWidget(titulo)
        cab.addStretch(1)
        self.btn_novo = QPushButton("+  Nova contagem")
        self.btn_novo.setCursor(Qt.PointingHandCursor)
        cab.addWidget(self.btn_novo)
        lay.addLayout(cab)
        self.miolo = QWidget()
        self.caixa = QVBoxLayout(self.miolo)
        self.caixa.setContentsMargins(0, 0, 0, 0)
        self.caixa.setSpacing(8)
        lay.addWidget(_rolagem(self.miolo), 1)
        self.vazio = QLabel("Nenhuma contagem ainda.\nCrie uma para provas, viagens e aniversários.")
        self.vazio.setAlignment(Qt.AlignCenter)
        self.vazio.setObjectName("mensagemVazia")
        lay.addWidget(self.vazio, 1)
        self.btn_novo.clicked.connect(self.nova)
        self.atualizar()

    @property
    def contagens(self):
        return self.janela.servico.contagens_regressivas

    def atualizar(self):
        hoje = date.today()
        while self.caixa.count():
            w = self.caixa.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        lista = self.contagens.listar(hoje)
        for c in lista:
            self.caixa.addWidget(CartaoContagem(self, c, hoje))
        self.caixa.addStretch(1)
        self.vazio.setVisible(not lista)

    def nova(self, dados: dict | None = None):
        if not isinstance(dados, dict):
            dlg = DialogoContagem(self)
            if dlg.exec() != DialogoContagem.Accepted:
                return
            dados = dlg.resultado()
        self.contagens.criar(**dados)
        self.atualizar()

    def editar(self, c, dados: dict | None = None):
        if dados is None:
            dlg = DialogoContagem(self, c)
            if dlg.exec() != DialogoContagem.Accepted:
                return
            dados = dlg.resultado()
        c.nome, c.data, c.cor, c.anual = dados["nome"], dados["data"], dados["cor"], dados["anual"]
        self.contagens.salvar(c)
        self.atualizar()

    def apagar(self, c, confirmar: bool = True):
        if confirmar and QMessageBox.question(self, "Apagar contagem", f"Apagar “{c.nome}”?") != QMessageBox.Yes:
            return
        self.contagens.apagar(c.uuid)
        self.atualizar()


# ============================================================ Estatísticas
class GraficoBarras(QWidget):
    """Barras verticais simples, com linhas de grade e dica ao passar o mouse."""

    def __init__(self, cor: str, formatar=str):
        super().__init__()
        self.cor, self.formatar = cor, formatar
        self.dados: list[tuple[str, float, str]] = []     # (rótulo curto, valor, rótulo da dica)
        self.setMinimumHeight(170)
        self.setMouseTracking(True)
        self._barras: list[tuple[QRectF, int]] = []

    def definir(self, dados: list[tuple[str, float, str]]):
        self.dados = dados
        self.update()

    def paintEvent(self, _):
        pal = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._barras = []
        base = self.font()
        f = QFont(base)
        f.setPixelSize(10)
        p.setFont(f)
        esq, base_y, topo = 40, self.height() - 22, 8
        maximo = max((v for _, v, _ in self.dados), default=0)
        escala = self._escala(maximo)
        for i in range(5):
            y = base_y - (base_y - topo) * i / 4
            p.setPen(QPen(QColor(pal.borda), 1))
            p.drawLine(int(esq), int(y), self.width(), int(y))
            p.setPen(QColor(pal.apagado))
            p.drawText(QRectF(0, y - 8, esq - 6, 16), Qt.AlignRight | Qt.AlignVCenter,
                       self.formatar(escala * i / 4))
        n = len(self.dados)
        if n == 0:
            p.end()
            return
        larg = (self.width() - esq) / n
        passo_rotulo = max(1, n // 10)
        for i, (rotulo, valor, _) in enumerate(self.dados):
            x = esq + i * larg
            alt = (base_y - topo) * (valor / escala) if escala else 0
            r = QRectF(x + larg * 0.18, base_y - alt, larg * 0.64, alt)
            if valor > 0:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(self.cor))
                p.drawRoundedRect(r.adjusted(0, 0, 0, 3), 3, 3)
                p.drawRect(QRectF(r.left(), base_y - 3, r.width(), 3))
            self._barras.append((QRectF(x, topo, larg, base_y - topo), i))
            if i % passo_rotulo == 0:
                p.setPen(QColor(pal.apagado))
                p.drawText(QRectF(x - 10, base_y + 4, larg + 20, 16), Qt.AlignCenter, rotulo)
        p.end()

    @staticmethod
    def _escala(maximo: float) -> float:
        if maximo <= 0:
            return 4
        for passo in (4, 8, 12, 20, 40, 80, 120, 240, 480, 1200, 2400, 4800, 12000, 24000, 48000, 120000):
            if maximo <= passo:
                return passo
        return maximo

    def mouseMoveEvent(self, e):
        for r, i in self._barras:
            if r.contains(e.position()):
                QToolTip.showText(e.globalPosition().toPoint(), self.dados[i][2], self)
                return
        QToolTip.hideText()


class BarrasHorizontais(QWidget):
    """Uma barra por linha: nome, barra proporcional e valor."""

    def __init__(self, cor: str, sufixo: str = "", maximo: int | None = None):
        super().__init__()
        self.cor, self.sufixo, self.maximo = cor, sufixo, maximo
        self.itens: list[tuple[str, int]] = []

    def definir(self, itens: list[tuple[str, int]]):
        self.itens = itens[:8]
        self.setMinimumHeight(max(len(self.itens), 1) * 28 + 6)
        self.update()

    def paintEvent(self, _):
        pal = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        maximo = self.maximo or max((v for _, v in self.itens), default=1) or 1
        nome_larg = 150
        for i, (nome, v) in enumerate(self.itens):
            y = i * 28 + 3
            p.setPen(QColor(pal.texto))
            p.drawText(QRectF(0, y, nome_larg - 8, 22), Qt.AlignLeft | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(nome, Qt.ElideRight, nome_larg - 8))
            larg = min(self.width() - nome_larg - 60, 640) * v / maximo
            p.setPen(Qt.NoPen)
            p.setBrush(com_alfa(self.cor, 255))
            p.drawRoundedRect(QRectF(nome_larg, y + 4, max(larg, 3), 14), 4, 4)
            p.setPen(QColor(pal.apagado))
            p.drawText(QRectF(nome_larg + max(larg, 3) + 8, y, 54, 22), Qt.AlignLeft | Qt.AlignVCenter, f"{v}{self.sufixo}")
        p.end()


class PaginaEstatisticas(QWidget):
    PERIODOS = [("Últimos 7 dias", 7), ("Últimos 30 dias", 30), ("Últimos 90 dias", 90)]

    def __init__(self, janela):
        super().__init__()
        self.janela = janela
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 12)
        lay.setSpacing(10)
        cab = QHBoxLayout()
        titulo = QLabel("Estatísticas")
        titulo.setObjectName("titulo")
        cab.addWidget(titulo)
        cab.addStretch(1)
        self.combo = QComboBox()
        for nome, n in self.PERIODOS:
            self.combo.addItem(nome, n)
        self.combo.setCurrentIndex(1)
        cab.addWidget(self.combo)
        lay.addLayout(cab)
        self.miolo = QWidget()
        col = QVBoxLayout(self.miolo)
        col.setContentsMargins(0, 0, 8, 0)
        col.setSpacing(14)
        self.cartoes = QGridLayout()
        self.cartoes.setSpacing(10)
        self.numeros: dict[str, QLabel] = {}
        itens = [("concluidas_hoje", "Concluídas hoje"), ("concluidas_semana", "Concluídas em 7 dias"),
                 ("concluidas_total", "Concluídas no total"), ("pendentes", "Pendentes"),
                 ("atrasadas", "Atrasadas"), ("foco_hoje", "Foco hoje"), ("foco_semana", "Foco em 7 dias"),
                 ("sequencia", "Dias seguidos com tarefa")]
        for i, (chave, rotulo) in enumerate(itens):
            self.cartoes.addWidget(self._cartao(chave, rotulo), i // 4, i % 4)
        col.addLayout(self.cartoes)
        col.addWidget(self._secao("TAREFAS CONCLUÍDAS POR DIA"))
        self.g_tarefas = GraficoBarras(tema.atual.destaque, lambda v: str(int(round(v))))
        col.addWidget(self.g_tarefas)
        col.addWidget(self._secao("TEMPO DE FOCO POR DIA (MINUTOS)"))
        self.g_foco = GraficoBarras("#4dd0b1", lambda v: str(int(round(v))))
        col.addWidget(self.g_foco)
        col.addWidget(self._secao("CONCLUÍDAS POR LISTA"))
        self.g_listas = BarrasHorizontais("#f5a623")
        col.addWidget(self.g_listas)
        col.addWidget(self._secao("HÁBITOS (ÚLTIMOS 30 DIAS)"))
        self.g_habitos = BarrasHorizontais("#b57edc", "%", 100)
        col.addWidget(self.g_habitos)
        col.addStretch(1)
        lay.addWidget(_rolagem(self.miolo), 1)
        self.combo.currentIndexChanged.connect(lambda _: self.atualizar())
        self.atualizar()

    @staticmethod
    def _secao(texto: str) -> QLabel:
        r = QLabel(texto)
        r.setObjectName("secao")
        return r

    def _cartao(self, chave: str, rotulo: str) -> QFrame:
        pal = tema.atual
        q = QFrame()
        q.setStyleSheet(f"QFrame {{ background: {pal.barra}; border-radius: 10px; }}")
        l = QVBoxLayout(q)
        l.setContentsMargins(14, 10, 14, 10)
        l.setSpacing(0)
        num = QLabel("0")
        num.setStyleSheet("font-size: 24px; font-weight: 700; background: transparent;")
        rot = QLabel(rotulo)
        rot.setStyleSheet(f"font-size: 11px; color: {pal.apagado}; background: transparent;")
        l.addWidget(num)
        l.addWidget(rot)
        self.numeros[chave] = num
        return q

    def atualizar(self):
        svc = self.janela.servico
        hoje = date.today()
        n = self.combo.currentData()
        ini = hoje - timedelta(days=n - 1)
        r = svc.estatisticas.resumo(hoje)
        valores = {
            "concluidas_hoje": r.concluidas_hoje, "concluidas_semana": r.concluidas_semana,
            "concluidas_total": r.concluidas_total, "pendentes": r.pendentes, "atrasadas": r.atrasadas,
            "foco_hoje": formatar_duracao(r.foco_hoje_s), "foco_semana": formatar_duracao(r.foco_semana_s),
            "sequencia": r.sequencia_dias,
        }
        for chave, v in valores.items():
            self.numeros[chave].setText(str(v))
        dias_t = svc.estatisticas.concluidas_por_dia(ini, hoje)
        self.g_tarefas.definir([(f"{d.day}/{d.month}", v, f"{d:%d/%m}: {v} concluída{'s' if v != 1 else ''}")
                                for d, v in dias_t.items()])
        dias_f = svc.estatisticas.foco_por_dia(ini, hoje)
        self.g_foco.definir([(f"{d.day}/{d.month}", s / 60, f"{d:%d/%m}: {formatar_duracao(s)}")
                             for d, s in dias_f.items()])
        self.g_listas.definir(svc.estatisticas.por_lista())
        hab = svc.habitos
        todas = hab.todas_as_marcacoes()
        self.g_habitos.definir(sorted(
            ((h.nome, round(hab.taxa(h, hoje - timedelta(days=29), hoje, todas.get(h.uuid, {})) * 100))
             for h in hab.listar()), key=lambda x: -x[1]))
