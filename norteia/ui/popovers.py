"""Janelinhas flutuantes (popovers): seletor de data, cartão de tarefa, lista e etiquetas.

Seguem o jeito do app original: o cartão aparece junto do que você clicou, tem o chip de data, a bandeira de
prioridade, o título, a descrição ou lista de itens, e embaixo a lista e o menu "...". Fechar o cartão (clicar
fora, Esc ou Enter) grava a tarefa.
"""
from __future__ import annotations

import calendar as _calendar
import time as time_mod
from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QDate, QPoint, QRect, QRectF, QSize, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QPlainTextEdit, QPushButton, QSpinBox, QTimeEdit,
                               QVBoxLayout, QWidget)

from ..core import recorrencia
from ..core.models import Prioridade
from . import icones, tema
from .util import DIAS_CURTOS, MESES, com_alfa, rotulo_prazo

LEMBRETES_PADRAO = [(0, "Na hora"), (5, "5 minutos antes"), (30, "30 minutos antes"), (60, "1 hora antes"),
                    (1440, "1 dia antes")]
NOMES_PRIORIDADE = [(3, "Alta"), (2, "Média"), (1, "Baixa"), (0, "Nenhuma")]


def nome_lembrete(minutos: int) -> str:
    for m, nome in LEMBRETES_PADRAO:
        if m == minutos:
            return nome
    if minutos % 1440 == 0:
        n = minutos // 1440
        return f"{n} dia{'s' if n != 1 else ''} antes"
    if minutos % 60 == 0:
        n = minutos // 60
        return f"{n} hora{'s' if n != 1 else ''} antes"
    return f"{minutos} minutos antes"


def _qss() -> str:
    p = tema.atual
    return f"""
QFrame#flutuante {{ background: {p.barra}; border: 1px solid {p.borda}; border-radius: 10px; }}
QFrame#flutuante QLabel {{ background: transparent; }}
QFrame#flutuante QLineEdit#semBorda, QFrame#flutuante QPlainTextEdit#semBorda {{
    background: transparent; border: none; padding: 2px 0; selection-background-color: {p.destaque};
}}
QFrame#flutuante QPushButton#plano {{ background: transparent; border: none; padding: 4px 6px; border-radius: 6px; }}
QFrame#flutuante QPushButton#plano:hover {{ background: {p.barra_hover}; border: none; }}
QFrame#flutuante QPushButton#ok {{ background: {p.destaque}; border: none; color: white; font-weight: 600; }}
QFrame#flutuante QPushButton#ok:hover {{ background: #5a82ff; border: none; }}
QFrame#flutuante QPushButton#aba {{ background: transparent; border: none; border-radius: 6px; padding: 5px 10px;
    color: {p.apagado}; font-size: 12px; }}
QFrame#flutuante QPushButton#aba:checked {{ background: {p.barra_ativa}; color: {p.texto}; }}
QFrame#linhaOpcao {{ background: transparent; border-radius: 6px; }}
QFrame#linhaOpcao:hover {{ background: {p.barra_hover}; }}
QFrame#flutuante QListWidget {{ background: transparent; border: none; outline: none; }}
QFrame#flutuante QListWidget::item {{ padding: 6px 8px; border-radius: 6px; }}
QFrame#flutuante QListWidget::item:hover {{ background: {p.barra_hover}; }}
QFrame#flutuante QListWidget::item:selected {{ background: {p.barra_ativa}; }}
QFrame#flutuante QLineEdit {{ background: {p.campo}; border: 1px solid {p.borda}; border-radius: 6px;
    padding: 6px 8px; font-size: 12px; }}
"""


class Flutuante(QFrame):
    """Janelinha sem borda que fecha ao clicar fora."""

    def __init__(self, parent=None, popup: bool = True):
        if popup:
            super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        else:
            super().__init__(parent)
        self.setObjectName("flutuante")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor(tema.atual.barra))
        self.setPalette(pal)
        self.setStyleSheet(_qss())
        self._t_show = 0.0
        self._fecho_ok = True

    # Um fechamento que o Qt faz sozinho logo depois de abrir (troca de janela ativa, clique duplo, soltar do
    # mouse) fazia o cartão "piscar e sumir". Fechamentos nossos (Enter, OK, menus) passam por `close()`.
    def close(self):
        self._fecho_ok = True
        return super().close()

    def showEvent(self, e):
        self._t_show = time_mod.monotonic()
        self._fecho_ok = False
        super().showEvent(e)

    def _fecho_espurio(self) -> bool:
        return (not self._fecho_ok) and (time_mod.monotonic() - self._t_show) < 0.35

    def closeEvent(self, e):
        if self._fecho_espurio():
            e.ignore()
            return
        super().closeEvent(e)

    def mostrar_perto(self, global_pos: QPoint, retangulo_alvo: QRect | None = None):
        """Abre ao lado do retângulo (ou no ponto) sem sair da tela."""
        self.adjustSize()
        self.show()
        self.adjustSize()
        tela = self.screen().availableGeometry() if self.screen() else QRect(0, 0, 1920, 1080)
        w, h = self.width(), self.height()
        if retangulo_alvo is not None:
            x = retangulo_alvo.right() + 6
            if x + w > tela.right():
                x = retangulo_alvo.left() - w - 6
            y = retangulo_alvo.top()
        else:
            x, y = global_pos.x(), global_pos.y()
        x = max(tela.left() + 4, min(x, tela.right() - w - 4))
        y = max(tela.top() + 4, min(y, tela.bottom() - h - 4))
        self.move(x, y)


def _plano(texto: str = "", icone: str | None = None, cor: str | None = None, dica: str = "") -> QPushButton:
    b = QPushButton(texto)
    b.setObjectName("plano")
    b.setCursor(Qt.PointingHandCursor)
    if icone:
        b.setIcon(icones.icone(icone, cor or tema.atual.apagado, 16))
        b.setIconSize(QSize(16, 16))
    if dica:
        b.setToolTip(dica)
    return b


class LinhaOpcao(QFrame):
    """Linha clicável: ícone, texto, valor azul e seta (ou "x" para limpar)."""
    clicada = Signal()
    limpou = Signal()

    def __init__(self, icone: str, texto: str, limpavel: bool = False):
        super().__init__()
        self.setObjectName("linhaOpcao")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(30)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(8)
        self.ico = QLabel()
        self.ico.setFixedSize(16, 16)
        self.rot = QLabel(texto)
        self.rot.setStyleSheet("font-size: 12px;")
        self.seta = QLabel()
        self.seta.setFixedSize(14, 14)
        self.seta.setPixmap(icones.pixmap("seta-dir", tema.atual.apagado, 14))
        self.limpar = QPushButton()
        self.limpar.setObjectName("plano")
        self.limpar.setIcon(icones.icone("fechar", tema.atual.apagado, 12))
        self.limpar.setFixedSize(18, 18)
        self.limpar.setVisible(False)
        self.limpar.clicked.connect(self.limpou.emit)
        self._limpavel = limpavel
        self._icone = icone
        lay.addWidget(self.ico)
        lay.addWidget(self.rot, 1)
        lay.addWidget(self.limpar)
        lay.addWidget(self.seta)
        self.definir(texto, False)

    def definir(self, texto: str, ativo: bool):
        pal = tema.atual
        self.rot.setText(texto)
        cor = pal.destaque if ativo else pal.texto
        self.rot.setStyleSheet(f"font-size: 12px; color: {cor};")
        self.ico.setPixmap(icones.pixmap(self._icone, pal.destaque if ativo else pal.apagado, 16))
        self.limpar.setVisible(ativo and self._limpavel)
        self.seta.setVisible(not (ativo and self._limpavel))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicada.emit()


class GradeDias(QWidget):
    """Grade do mês para escolher um dia."""
    escolhido = Signal(object)
    COL = 33
    LIN = 26
    CAB = 20

    def __init__(self, segunda_primeiro: bool = False):
        super().__init__()
        self.segunda = segunda_primeiro
        self.mes = date.today().replace(day=1)
        self.selecionado: date | None = None
        self.hoje = date.today()
        self.setFixedSize(self.COL * 7, self.CAB + self.LIN * 6)
        self.setMouseTracking(True)
        self._hover: date | None = None
        self.celulas: dict[date, QRect] = {}

    def dias(self) -> list[date]:
        primeiro = self.mes
        ini = primeiro - timedelta(days=(primeiro.weekday() if self.segunda else (primeiro.weekday() + 1) % 7))
        return [ini + timedelta(days=i) for i in range(42)]

    def definir_mes(self, d: date):
        self.mes = d.replace(day=1)
        self.update()

    def deslocar(self, passo: int):
        m = self.mes.month - 1 + passo
        self.mes = date(self.mes.year + m // 12, m % 12 + 1, 1)
        self.update()

    def paintEvent(self, _):
        pal = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont(self.font())
        f.setPixelSize(10)
        p.setFont(f)
        p.setPen(QColor(pal.apagado))
        nomes = ["S", "T", "Q", "Q", "S", "S", "D"] if self.segunda else ["D", "S", "T", "Q", "Q", "S", "S"]
        for i, n in enumerate(nomes):
            p.drawText(QRect(i * self.COL, 0, self.COL, self.CAB), Qt.AlignCenter, n)
        f.setPixelSize(12)
        self.celulas = {}
        for i, d in enumerate(self.dias()):
            r = QRect((i % 7) * self.COL, self.CAB + (i // 7) * self.LIN, self.COL, self.LIN)
            self.celulas[d] = r
            centro = r.center()
            if d == self.selecionado:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(pal.destaque))
                p.drawEllipse(centro, 11, 11)
                p.setPen(QColor(pal.sobre_destaque))
                f.setBold(True)
            else:
                if d == self._hover:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(pal.barra_ativa))
                    p.drawEllipse(centro, 11, 11)
                f.setBold(d == self.hoje)
                if d == self.hoje:
                    p.setPen(QColor(pal.destaque))
                elif d.month == self.mes.month:
                    p.setPen(QColor(pal.texto))
                else:
                    p.setPen(QColor("#5a5a5a"))
            p.setFont(f)
            p.drawText(r, Qt.AlignCenter, str(d.day))
        p.end()

    def _dia_em(self, pos: QPoint) -> date | None:
        for d, r in self.celulas.items():
            if r.contains(pos):
                return d
        return None

    def mouseMoveEvent(self, e):
        d = self._dia_em(e.position().toPoint())
        if d != self._hover:
            self._hover = d
            self.update()

    def leaveEvent(self, _):
        self._hover = None
        self.update()

    def mousePressEvent(self, e):
        d = self._dia_em(e.position().toPoint())
        if d is not None and e.button() == Qt.LeftButton:
            self.selecionado = d
            if d.month != self.mes.month:
                self.mes = d.replace(day=1)
            self.update()
            self.escolhido.emit(d)


def _sem_hora_arredondada() -> time:
    agora = datetime.now() + timedelta(hours=1)
    return time(agora.hour, 0)


class SeletorData(Flutuante):
    """Escolhe data (aba "Data") ou período com início e fim (aba "Duração"), hora, lembrete e repetição.

    `estado` tem: prazo, hora, inicio, duracao_min, lembretes, repeticao. Ao clicar em OK emite `aplicado(dict)`
    com as mesmas chaves (prazo None = sem data)."""
    aplicado = Signal(dict)

    def __init__(self, estado: dict, parent=None, segunda_primeiro: bool = False):
        super().__init__(parent)
        self.setFixedWidth(262)
        hoje = date.today()
        self.hoje = hoje
        self.dia: date | None = estado.get("prazo")
        self.hora: time | None = estado.get("hora")
        self.lembretes: list[int] = list(estado.get("lembretes") or [])
        self.repeticao: str | None = estado.get("repeticao")
        inicio = estado.get("inicio")
        dur = estado.get("duracao_min") or 0
        self.d0: date = inicio or self.dia or hoje
        self.d1: date = self.dia or self.d0
        self.t0: time = self.hora or _sem_hora_arredondada()
        total = self.t0.hour * 60 + self.t0.minute + (dur or 60)
        self.t1: time = time(min(total, 24 * 60 - 1) // 60, min(total, 24 * 60 - 1) % 60)
        self.dia_inteiro: bool = self.hora is None
        self._dur_orig = dur
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(4)

        abas = QFrame()
        abas.setStyleSheet(f"QFrame {{ background: {tema.atual.campo}; border-radius: 8px; }}")
        la = QHBoxLayout(abas)
        la.setContentsMargins(3, 3, 3, 3)
        la.setSpacing(2)
        self.aba_data = QPushButton("Data")
        self.aba_dur = QPushButton("Duração")
        for b in (self.aba_data, self.aba_dur):
            b.setObjectName("aba")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            la.addWidget(b, 1)
        lay.addWidget(abas)

        # ---- aba Data ----
        self.pg_data = QWidget()
        lp = QVBoxLayout(self.pg_data)
        lp.setContentsMargins(0, 4, 0, 0)
        lp.setSpacing(2)
        rapidos = QHBoxLayout()
        self.rapidos: dict[str, QPushButton] = {}
        for chave, icone, dica in (("hoje", "sol", "Hoje"), ("amanha", "nascer-do-sol", "Amanhã"),
                                   ("semana", "calendario", "Próxima semana"), ("mes", "lua", "Próximo mês")):
            b = _plano(icone=icone, cor=tema.atual.texto, dica=dica)
            b.setFixedSize(54, 32)
            b.setIconSize(QSize(20, 20))
            b.clicked.connect(lambda _=False, c=chave: self.atalho(c))
            self.rapidos[chave] = b
            rapidos.addWidget(b)
        lp.addLayout(rapidos)
        cab = QHBoxLayout()
        cab.setContentsMargins(4, 0, 0, 0)
        self.rot_mes = QLabel()
        self.rot_mes.setStyleSheet("font-size: 12px; font-weight: 600;")
        cab.addWidget(self.rot_mes, 1)
        self.btn_mes_ant = _plano(icone="seta-esq", dica="Mês anterior")
        self.btn_mes_hoje = _plano(icone="circulo", dica="Hoje")
        self.btn_mes_prox = _plano(icone="seta-dir", dica="Próximo mês")
        for b in (self.btn_mes_ant, self.btn_mes_hoje, self.btn_mes_prox):
            b.setFixedSize(24, 24)
            cab.addWidget(b)
        lp.addLayout(cab)
        self.grade = GradeDias(segunda_primeiro)
        self.grade.selecionado = self.dia
        self.grade.definir_mes(self.dia or hoje)
        lp.addWidget(self.grade, 0, Qt.AlignHCenter)
        lay.addWidget(self.pg_data)

        # ---- aba Duração ----
        self.pg_dur = QWidget()
        ld = QVBoxLayout(self.pg_dur)
        ld.setContentsMargins(0, 8, 0, 4)
        ld.setSpacing(8)
        self.ed_d0, self.ed_t0 = QDateEdit(), QTimeEdit()
        self.ed_d1, self.ed_t1 = QDateEdit(), QTimeEdit()
        for ed in (self.ed_d0, self.ed_d1):
            ed.setCalendarPopup(True)
            ed.setDisplayFormat("dd/MM")
        for ed in (self.ed_t0, self.ed_t1):
            ed.setDisplayFormat("HH:mm")
        for nome, de, te in (("Começar", self.ed_d0, self.ed_t0), ("Fim", self.ed_d1, self.ed_t1)):
            h = QHBoxLayout()
            rot = QLabel(nome)
            rot.setFixedWidth(52)
            rot.setStyleSheet("font-size: 12px;")
            h.addWidget(rot)
            h.addWidget(de, 1)
            h.addWidget(te, 1)
            ld.addLayout(h)
        h = QHBoxLayout()
        rot = QLabel("Dia inteiro")
        rot.setStyleSheet("font-size: 12px;")
        h.addWidget(rot, 1)
        self.chk_dia_inteiro = QCheckBox()
        self.chk_dia_inteiro.setToolTip("Sem hora marcada")
        h.addWidget(self.chk_dia_inteiro)
        ld.addLayout(h)
        lay.addWidget(self.pg_dur)

        # ---- linhas comuns ----
        self.l_hora = LinhaOpcao("relogio", "Hora", limpavel=True)
        self.l_lembrete = LinhaOpcao("sino", "Lembrete", limpavel=True)
        self.l_repetir = LinhaOpcao("repetir", "Repetir", limpavel=True)
        lay.addWidget(self.l_hora)
        self.p_hora = self._painel_hora()
        lay.addWidget(self.p_hora)
        lay.addWidget(self.l_lembrete)
        self.p_lembrete = self._painel_lembrete()
        lay.addWidget(self.p_lembrete)
        lay.addWidget(self.l_repetir)
        self.p_repetir = self._painel_repetir()
        lay.addWidget(self.p_repetir)

        botoes = QHBoxLayout()
        botoes.setSpacing(8)
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setObjectName("ok")
        self.btn_limpar = QPushButton("Limpar")
        for b in (self.btn_ok, self.btn_limpar):
            b.setCursor(Qt.PointingHandCursor)
            botoes.addWidget(b, 1)
        lay.addSpacing(4)
        lay.addLayout(botoes)

        self.aba_data.clicked.connect(lambda: self.escolher_aba(0))
        self.aba_dur.clicked.connect(lambda: self.escolher_aba(1))
        self.grade.escolhido.connect(self._dia_escolhido)
        self.btn_mes_ant.clicked.connect(lambda: (self.grade.deslocar(-1), self._rotular_mes()))
        self.btn_mes_prox.clicked.connect(lambda: (self.grade.deslocar(1), self._rotular_mes()))
        self.btn_mes_hoje.clicked.connect(lambda: (self.grade.definir_mes(self.hoje), self._rotular_mes()))
        self.l_hora.clicada.connect(lambda: self._alternar(self.p_hora))
        self.l_lembrete.clicada.connect(lambda: self._alternar(self.p_lembrete))
        self.l_repetir.clicada.connect(lambda: self._alternar(self.p_repetir))
        self.l_hora.limpou.connect(self._limpar_hora)
        self.l_lembrete.limpou.connect(self._limpar_lembrete)
        self.l_repetir.limpou.connect(lambda: self._definir_repeticao(None))
        self.chk_dia_inteiro.toggled.connect(self._ao_dia_inteiro)
        for ed in (self.ed_d0, self.ed_d1):
            ed.dateChanged.connect(self._ao_mudar_duracao)
        for ed in (self.ed_t0, self.ed_t1):
            ed.timeChanged.connect(self._ao_mudar_duracao)
        self.btn_ok.clicked.connect(self.confirmar)
        self.btn_limpar.clicked.connect(self.limpar)

        self.escolher_aba(1 if (inicio and inicio != self.dia) else 0)
        self._rotular_mes()
        self._atualizar_linhas()

    # ---- painéis internos ----
    def _painel_hora(self) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(8, 0, 8, 4)
        self.ed_hora = QTimeEdit()
        self.ed_hora.setDisplayFormat("HH:mm")
        t = self.hora or self.t0
        self.ed_hora.setTime(QTime(t.hour, t.minute))
        self.ed_hora.timeChanged.connect(self._ao_mudar_hora)
        h.addWidget(self.ed_hora, 1)
        b = QPushButton("Sem hora")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(self._limpar_hora)
        h.addWidget(b)
        w.setVisible(False)
        return w

    def _painel_lembrete(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 0, 8, 4)
        v.setSpacing(2)
        self.chks_lembrete: dict[int, QCheckBox] = {}
        for m, nome in LEMBRETES_PADRAO:
            c = QCheckBox(nome)
            c.setChecked(m in self.lembretes)
            self.chks_lembrete[m] = c
            v.addWidget(c)
        self.caixa_extra_lembrete = QVBoxLayout()
        v.addLayout(self.caixa_extra_lembrete)
        pers = QHBoxLayout()
        self.sp_lembrete = QSpinBox()
        self.sp_lembrete.setRange(1, 999)
        self.sp_lembrete.setValue(10)
        self.un_lembrete = QComboBox()
        for nome, f in (("minutos antes", 1), ("horas antes", 60), ("dias antes", 1440)):
            self.un_lembrete.addItem(nome, f)
        pers.addWidget(self.sp_lembrete)
        pers.addWidget(self.un_lembrete, 1)
        v.addLayout(pers)
        bs = QHBoxLayout()
        self.btn_salvar_lembrete = QPushButton("Salvar")
        self.btn_salvar_lembrete.setObjectName("ok")
        self.btn_cancelar_lembrete = QPushButton("Cancelar")
        for b in (self.btn_salvar_lembrete, self.btn_cancelar_lembrete):
            b.setCursor(Qt.PointingHandCursor)
            bs.addWidget(b)
        v.addLayout(bs)
        self.btn_salvar_lembrete.clicked.connect(self._salvar_lembrete)
        self.btn_cancelar_lembrete.clicked.connect(lambda: self._alternar(self.p_lembrete, False))
        self._extras_lembrete: dict[int, QCheckBox] = {}
        self._montar_extras_lembrete()
        w.setVisible(False)
        return w

    def _montar_extras_lembrete(self):
        for c in self._extras_lembrete.values():
            c.setParent(None)
        self._extras_lembrete = {}
        for m in self.lembretes:
            if m not in self.chks_lembrete:
                c = QCheckBox(nome_lembrete(m))
                c.setChecked(True)
                self._extras_lembrete[m] = c
                self.caixa_extra_lembrete.addWidget(c)

    def _painel_repetir(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 0, 8, 4)
        v.setSpacing(1)
        self.botoes_repetir: dict[str, QPushButton] = {}
        self.pg_repetir_lista = QWidget()
        vl = QVBoxLayout(self.pg_repetir_lista)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(1)
        v.addWidget(self.pg_repetir_lista)
        self._itens_repetir = {}
        for chave in ("DIARIO", "SEMANAL", "MENSAL", "ANUAL", "UTEIS", "PERSONALIZADO"):
            b = _plano("")
            b.setStyleSheet("text-align: left; font-size: 12px;")
            b.clicked.connect(lambda _=False, c=chave: self._escolher_repeticao(c))
            self.botoes_repetir[chave] = b
            vl.addWidget(b)
        # personalizado em linha
        self.pg_repetir_pers = QWidget()
        vp = QVBoxLayout(self.pg_repetir_pers)
        vp.setContentsMargins(0, 0, 0, 0)
        vp.setSpacing(6)
        h = QHBoxLayout()
        h.addWidget(QLabel("A cada"))
        self.sp_intervalo = QSpinBox()
        self.sp_intervalo.setRange(1, 99)
        self.cb_freq = QComboBox()
        for chave, nome in (("DAILY", "Dia"), ("WEEKLY", "Semana"), ("MONTHLY", "Mês"), ("YEARLY", "Ano")):
            self.cb_freq.addItem(nome, chave)
        self.cb_freq.setCurrentIndex(1)
        h.addWidget(self.sp_intervalo)
        h.addWidget(self.cb_freq, 1)
        vp.addLayout(h)
        self.dias_repetir = []
        hd = QHBoxLayout()
        hd.setSpacing(3)
        for i, ini in enumerate(["S", "T", "Q", "Q", "S", "S", "D"]):
            b = QPushButton(ini)
            b.setCheckable(True)
            b.setFixedSize(26, 26)
            b.setStyleSheet(f"QPushButton {{ padding: 0; border-radius: 13px; font-size: 11px; }}"
                            f"QPushButton:checked {{ background: {tema.atual.destaque}; border-color: "
                            f"{tema.atual.destaque}; color: white; }}")
            self.dias_repetir.append(b)
            hd.addWidget(b)
        self.caixa_dias_repetir = QWidget()
        self.caixa_dias_repetir.setLayout(hd)
        vp.addWidget(self.caixa_dias_repetir)
        hf = QHBoxLayout()
        self.cb_fim = QComboBox()
        for nome, chave in (("Nunca termina", "nunca"), ("Termina em", "data"), ("Termina após", "vezes")):
            self.cb_fim.addItem(nome, chave)
        self.ed_fim_rep = QDateEdit()
        self.ed_fim_rep.setCalendarPopup(True)
        self.ed_fim_rep.setDisplayFormat("dd/MM/yyyy")
        d = self.hoje + timedelta(days=90)
        self.ed_fim_rep.setDate(QDate(d.year, d.month, d.day))
        self.sp_vezes = QSpinBox()
        self.sp_vezes.setRange(1, 999)
        self.sp_vezes.setValue(10)
        self.sp_vezes.setSuffix(" vezes")
        hf.addWidget(self.cb_fim, 1)
        hf.addWidget(self.ed_fim_rep)
        hf.addWidget(self.sp_vezes)
        vp.addLayout(hf)
        hb = QHBoxLayout()
        self.btn_aplicar_rep = QPushButton("OK")
        self.btn_aplicar_rep.setObjectName("ok")
        self.btn_cancelar_rep = QPushButton("Cancelar")
        for b in (self.btn_aplicar_rep, self.btn_cancelar_rep):
            b.setCursor(Qt.PointingHandCursor)
            hb.addWidget(b)
        vp.addLayout(hb)
        v.addWidget(self.pg_repetir_pers)
        self.pg_repetir_pers.setVisible(False)
        self.cb_freq.currentIndexChanged.connect(self._ajustar_repetir_pers)
        self.cb_fim.currentIndexChanged.connect(self._ajustar_repetir_pers)
        self.btn_aplicar_rep.clicked.connect(self._aplicar_repeticao_pers)
        self.btn_cancelar_rep.clicked.connect(self._cancelar_repeticao_pers)
        w.setVisible(False)
        return w

    def _ajustar_repetir_pers(self, *_):
        self.caixa_dias_repetir.setVisible(self.cb_freq.currentData() == "WEEKLY")
        self.ed_fim_rep.setVisible(self.cb_fim.currentData() == "data")
        self.sp_vezes.setVisible(self.cb_fim.currentData() == "vezes")
        self.adjustSize()

    def _referencia(self) -> date:
        return (self.d1 if self.aba_dur.isChecked() else self.dia) or self.hoje

    def _rotular_repeticoes(self):
        d = self._referencia()
        textos = {
            "DIARIO": "Diariamente",
            "SEMANAL": f"Semanal ({DIAS_CURTOS[d.weekday()]})",
            "MENSAL": f"Mensal ({d.day}º)",
            "ANUAL": f"Anualmente ({d.day} de {MESES[d.month - 1][:3]})",
            "UTEIS": "Todos os dias úteis (Seg - Sex)",
            "PERSONALIZADO": "Personalizado",
        }
        for k, b in self.botoes_repetir.items():
            b.setText(textos[k])

    # ---- estado ----
    def escolher_aba(self, n: int):
        self.aba_data.setChecked(n == 0)
        self.aba_dur.setChecked(n == 1)
        self.pg_data.setVisible(n == 0)
        self.pg_dur.setVisible(n == 1)
        self.l_hora.setVisible(n == 0)
        if n == 0:
            self.p_hora.setVisible(False)
        else:
            self._carregar_duracao()
        self._atualizar_linhas()
        self.adjustSize()

    def _carregar_duracao(self):
        for ed, d in ((self.ed_d0, self.d0), (self.ed_d1, self.d1)):
            ed.blockSignals(True)
            ed.setDate(QDate(d.year, d.month, d.day))
            ed.blockSignals(False)
        for ed, t in ((self.ed_t0, self.t0), (self.ed_t1, self.t1)):
            ed.blockSignals(True)
            ed.setTime(QTime(t.hour, t.minute))
            ed.blockSignals(False)
        self.chk_dia_inteiro.blockSignals(True)
        self.chk_dia_inteiro.setChecked(self.dia_inteiro)
        self.chk_dia_inteiro.blockSignals(False)
        self.ed_t0.setEnabled(not self.dia_inteiro)
        self.ed_t1.setEnabled(not self.dia_inteiro)

    def _ao_mudar_duracao(self, *_):
        q = self.ed_d0.date()
        self.d0 = date(q.year(), q.month(), q.day())
        q = self.ed_d1.date()
        self.d1 = date(q.year(), q.month(), q.day())
        a, b = self.ed_t0.time(), self.ed_t1.time()
        self.t0, self.t1 = time(a.hour(), a.minute()), time(b.hour(), b.minute())
        if self.d1 < self.d0:
            self.d1 = self.d0
            self.ed_d1.blockSignals(True)
            self.ed_d1.setDate(QDate(self.d1.year, self.d1.month, self.d1.day))
            self.ed_d1.blockSignals(False)
        self.dia = self.d1
        self._atualizar_linhas()

    def _ao_dia_inteiro(self, ligado: bool):
        self.dia_inteiro = ligado
        self.ed_t0.setEnabled(not ligado)
        self.ed_t1.setEnabled(not ligado)
        self.hora = None if ligado else self.t0
        self._atualizar_linhas()

    def _dia_escolhido(self, d: date):
        self.dia = d
        self.d0 = self.d1 = d
        self._rotular_mes()
        self._atualizar_linhas()

    def atalho(self, chave: str):
        h = self.hoje
        if chave == "hoje":
            d = h
        elif chave == "amanha":
            d = h + timedelta(days=1)
        elif chave == "semana":
            d = h + timedelta(days=7 - h.weekday())
        else:
            m = h.month % 12 + 1
            ano = h.year + (1 if h.month == 12 else 0)
            d = date(ano, m, min(h.day, _calendar.monthrange(ano, m)[1]))
        self.grade.selecionado = d
        self.grade.definir_mes(d)
        self._dia_escolhido(d)

    def _rotular_mes(self):
        m = self.grade.mes
        self.rot_mes.setText(f"{MESES[m.month - 1][:3]} de {m.year}")

    def _ao_mudar_hora(self, q: QTime):
        self.hora = time(q.hour(), q.minute())
        self.t0 = self.hora
        if not self.lembretes:
            self.lembretes = [0]
            self._sincronizar_lembretes()
        self._atualizar_linhas()

    def _limpar_hora(self):
        self.hora = None
        self.dia_inteiro = True
        self.p_hora.setVisible(False)
        self._atualizar_linhas()
        self.adjustSize()

    def _limpar_lembrete(self):
        self.lembretes = []
        self._sincronizar_lembretes()
        self._atualizar_linhas()

    def _sincronizar_lembretes(self):
        for m, c in self.chks_lembrete.items():
            c.setChecked(m in self.lembretes)
        self._montar_extras_lembrete()

    def _salvar_lembrete(self):
        escolhidos = [m for m, c in self.chks_lembrete.items() if c.isChecked()]
        escolhidos += [m for m, c in self._extras_lembrete.items() if c.isChecked()]
        if self.sp_lembrete.value() and self._pediu_personalizado():
            m = self.sp_lembrete.value() * self.un_lembrete.currentData()
            if m not in escolhidos:
                escolhidos.append(m)
        self.lembretes = sorted(set(escolhidos))
        self._sincronizar_lembretes()
        self._alternar(self.p_lembrete, False)
        self._atualizar_linhas()

    def _pediu_personalizado(self) -> bool:
        return self.sp_lembrete.value() != 10 or self.un_lembrete.currentIndex() != 0

    def _escolher_repeticao(self, chave: str):
        if chave == "PERSONALIZADO":
            base = recorrencia.analisar(self.repeticao) or {"freq": "WEEKLY", "intervalo": 1, "dias": [],
                                                              "ate": None, "vezes": None}
            self.sp_intervalo.setValue(base["intervalo"])
            self.cb_freq.setCurrentIndex(max(self.cb_freq.findData(base["freq"]), 0))
            for i, b in enumerate(self.dias_repetir):
                b.setChecked(i in base["dias"])
            self.cb_fim.setCurrentIndex(1 if base["ate"] else 2 if base["vezes"] else 0)
            if base["vezes"]:
                self.sp_vezes.setValue(base["vezes"])
            self.pg_repetir_lista.setVisible(False)
            self.pg_repetir_pers.setVisible(True)
            self._ajustar_repetir_pers()
            return
        regra = {"DIARIO": "FREQ=DAILY", "SEMANAL": "FREQ=WEEKLY", "MENSAL": "FREQ=MONTHLY",
                 "ANUAL": "FREQ=YEARLY", "UTEIS": recorrencia.DIAS_UTEIS}[chave]
        self._definir_repeticao(regra)

    def _aplicar_repeticao_pers(self):
        fim = self.cb_fim.currentData()
        q = self.ed_fim_rep.date()
        regra = recorrencia.construir(
            self.cb_freq.currentData(), self.sp_intervalo.value(),
            [i for i, b in enumerate(self.dias_repetir) if b.isChecked()],
            ate=date(q.year(), q.month(), q.day()) if fim == "data" else None,
            vezes=self.sp_vezes.value() if fim == "vezes" else None)
        self._definir_repeticao(regra)

    def _cancelar_repeticao_pers(self):
        self.pg_repetir_pers.setVisible(False)
        self.pg_repetir_lista.setVisible(True)
        self._alternar(self.p_repetir, False)

    def _definir_repeticao(self, regra: str | None):
        self.repeticao = regra
        self.pg_repetir_pers.setVisible(False)
        self.pg_repetir_lista.setVisible(True)
        self._alternar(self.p_repetir, False)
        self._atualizar_linhas()

    def _alternar(self, painel: QWidget, ver: bool | None = None):
        ver = (not painel.isVisible()) if ver is None else ver
        for p in (self.p_hora, self.p_lembrete, self.p_repetir):
            if p is not painel:
                p.setVisible(False)
        painel.setVisible(ver)
        if ver and painel is self.p_hora and self.hora is None:
            q = self.ed_hora.time()
            self.hora = time(q.hour(), q.minute())
            self.dia_inteiro = False
            if not self.lembretes:
                self.lembretes = [0]
                self._sincronizar_lembretes()
            self._atualizar_linhas()
        if ver and painel is self.p_repetir:
            self._rotular_repeticoes()
            self.pg_repetir_pers.setVisible(False)
            self.pg_repetir_lista.setVisible(True)
        self.adjustSize()

    def _atualizar_linhas(self):
        hora = None if self.dia_inteiro and self.aba_dur.isChecked() else self.hora
        if self.aba_dur.isChecked():
            hora = None if self.dia_inteiro else self.t0
        self.l_hora.definir(hora.strftime("%H:%M") if hora and self.aba_data.isChecked() else "Hora",
                            bool(hora) and self.aba_data.isChecked())
        if self.lembretes:
            partes = [nome_lembrete(m) for m in self.lembretes[:2]]
            texto = ", ".join(partes) + ("…" if len(self.lembretes) > 2 else "")
            self.l_lembrete.definir(texto, True)
        else:
            self.l_lembrete.definir("Lembrete", False)
        if self.repeticao:
            self.l_repetir.definir(recorrencia.descrever(self.repeticao), True)
        else:
            self.l_repetir.definir("Repetir", False)
        self._rotular_repeticoes()

    # ---- resultado ----
    def resultado(self) -> dict:
        if self.aba_dur.isChecked():
            d0, d1 = self.d0, max(self.d1, self.d0)
            if self.dia_inteiro:
                hora, dur = None, 0
            else:
                hora = self.t0
                if d0 == d1:
                    m = (self.t1.hour * 60 + self.t1.minute) - (self.t0.hour * 60 + self.t0.minute)
                    dur = max(m, 15)
                else:
                    dur = 0
            lembretes = self.lembretes if (hora is not None or self.lembretes) else []
            return {"prazo": d1, "hora": hora, "inicio": d0 if d0 != d1 else None, "duracao_min": dur,
                    "lembretes": list(lembretes), "repeticao": self.repeticao}
        return {"prazo": self.dia, "hora": self.hora if self.dia else None, "inicio": None,
                "duracao_min": self._dur_orig if self.hora else 0,
                "lembretes": list(self.lembretes) if self.dia else [],
                "repeticao": self.repeticao if self.dia else None}

    def confirmar(self):
        r = self.resultado()
        if r["prazo"] is None and not self.aba_dur.isChecked():
            r = {"prazo": None, "hora": None, "inicio": None, "duracao_min": 0, "lembretes": [], "repeticao": None}
        self.aplicado.emit(r)
        self.close()

    def limpar(self):
        self.aplicado.emit({"prazo": None, "hora": None, "inicio": None, "duracao_min": 0, "lembretes": [],
                            "repeticao": None})
        self.close()


class SeletorLista(Flutuante):
    """Lista com busca: Caixa de Entrada e as listas do usuário."""
    escolhida = Signal(object)         # id da lista ou None (Caixa de Entrada)

    def __init__(self, projetos, atual: int | None, parent=None):
        super().__init__(parent)
        self.setFixedWidth(210)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar")
        lay.addWidget(self.busca)
        self.lista = QListWidget()
        self.lista.setFixedHeight(190)
        lay.addWidget(self.lista)
        self._todos = [(None, "Caixa de Entrada", tema.atual.destaque, "caixa")] + [
            (p.id, p.nome, p.cor, "lista") for p in projetos]
        self.atual = atual
        self.busca.textChanged.connect(self._filtrar)
        self.lista.itemClicked.connect(self._clicou)
        self._filtrar("")

    def _filtrar(self, texto: str):
        self.lista.clear()
        q = texto.strip().lower()
        for pid, nome, cor, ico in self._todos:
            if q and q not in nome.lower():
                continue
            it = QListWidgetItem(icones.icone(ico, tema.atual.apagado if pid else tema.atual.destaque, 16),
                                 nome + ("   ✓" if pid == self.atual else ""))
            it.setData(Qt.UserRole, pid)
            if pid == self.atual:
                it.setForeground(QColor(tema.atual.destaque))
            self.lista.addItem(it)

    def _clicou(self, item: QListWidgetItem):
        self.escolhida.emit(item.data(Qt.UserRole))
        self.close()


class SeletorTags(Flutuante):
    """Escolhe etiquetas existentes ou cria uma digitando."""
    escolhidas = Signal(list)

    def __init__(self, existentes: list[str], marcadas: list[str], parent=None):
        super().__init__(parent)
        self.setFixedWidth(210)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        self.campo = QLineEdit()
        self.campo.setPlaceholderText("Insira uma tag")
        lay.addWidget(self.campo)
        self.lista = QListWidget()
        self.lista.setFixedHeight(130)
        lay.addWidget(self.lista)
        self.vazio = QLabel("Sem tags")
        self.vazio.setAlignment(Qt.AlignCenter)
        self.vazio.setStyleSheet(f"color: {tema.atual.apagado}; font-size: 12px;")
        lay.addWidget(self.vazio)
        h = QHBoxLayout()
        self.btn_salvar = QPushButton("Salvar")
        self.btn_salvar.setObjectName("ok")
        self.btn_cancelar = QPushButton("Cancelar")
        for b in (self.btn_salvar, self.btn_cancelar):
            b.setCursor(Qt.PointingHandCursor)
            h.addWidget(b, 1)
        lay.addLayout(h)
        self.nomes = list(dict.fromkeys(list(existentes) + list(marcadas)))
        self.marcadas = list(marcadas)
        self._montar()
        self.campo.returnPressed.connect(self._adicionar)
        self.lista.itemChanged.connect(self._mudou)
        self.btn_salvar.clicked.connect(self._salvar)
        self.btn_cancelar.clicked.connect(self.close)

    def _montar(self):
        self.lista.blockSignals(True)
        self.lista.clear()
        for n in self.nomes:
            it = QListWidgetItem(f"#{n}")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if n in self.marcadas else Qt.Unchecked)
            it.setData(Qt.UserRole, n)
            self.lista.addItem(it)
        self.lista.blockSignals(False)
        self.vazio.setVisible(not self.nomes)
        self.lista.setVisible(bool(self.nomes))

    def _adicionar(self):
        nome = self.campo.text().strip().lstrip("#").lower()
        if not nome:
            return
        if nome not in self.nomes:
            self.nomes.append(nome)
        if nome not in self.marcadas:
            self.marcadas.append(nome)
        self.campo.clear()
        self._montar()

    def _mudou(self, item: QListWidgetItem):
        n = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked and n not in self.marcadas:
            self.marcadas.append(n)
        elif item.checkState() != Qt.Checked and n in self.marcadas:
            self.marcadas.remove(n)

    def _salvar(self):
        if self.campo.text().strip():
            self._adicionar()
        self.escolhidas.emit(list(self.marcadas))
        self.close()


class EditorDescricao(QPlainTextEdit):
    """Caixa de descrição: vazia mostra "Descrição"; ao clicar, a dica de uso aparece e o cursor pisca."""
    CURTO = "Descrição"
    LONGO = 'Digite o conteúdo ou use "/" para o menu'

    def __init__(self, texto: str = ""):
        super().__init__(texto)
        self.setPlaceholderText(self.CURTO)

    def focusInEvent(self, e):
        self.setPlaceholderText(self.LONGO)
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        self.setPlaceholderText(self.CURTO)
        super().focusOutEvent(e)


class CartaoTarefa(Flutuante):
    """Cartão flutuante para criar ou editar uma tarefa sem sair da tela."""
    salvou = Signal(object)

    def __init__(self, janela, tarefa=None, prazo: date | None = None, hora: time | None = None,
                 projeto_id: int | None = None, acoplado: bool = False):
        super().__init__(janela, popup=not acoplado)
        self.janela = janela
        self.servico = janela.servico
        self.t = tarefa
        self.acoplado = acoplado          # True: ampliado e fixo na lateral da lista (grava sozinho)
        self._feito = False
        self._abertos: list = []
        self.mod: set[str] = set()
        if acoplado:
            pal0 = tema.atual
            self.setStyleSheet(self.styleSheet() + f"QFrame#flutuante {{ background: {pal0.painel}; "
                               f"border: none; border-left: 1px solid {pal0.borda}; border-radius: 0; }}")
            fundo = self.palette()
            fundo.setColor(self.backgroundRole(), QColor(pal0.painel))
            self.setPalette(fundo)
            self._tempo_gravar = QTimer(self)
            self._tempo_gravar.setSingleShot(True)
            self._tempo_gravar.setInterval(600)
            self._tempo_gravar.timeout.connect(self.gravar_agora)
            self.setFixedWidth(440)
        else:
            self.setFixedWidth(312)
        if tarefa is not None:
            self.estado = {"prazo": tarefa.prazo, "hora": tarefa.prazo_hora, "inicio": tarefa.inicio,
                           "duracao_min": tarefa.duracao_min, "lembretes": list(tarefa.lembretes),
                           "repeticao": tarefa.repeticao}
            self.prio = int(tarefa.prioridade)
            self.tags = list(tarefa.tags)
            self.projeto_id = tarefa.projeto_id
        else:
            self.estado = {"prazo": prazo, "hora": hora, "inicio": None, "duracao_min": 0,
                           "lembretes": [0] if hora is not None else [], "repeticao": None}
            self.prio = 0
            self.tags = []
            self.projeto_id = projeto_id
        self._prefill = tarefa is None and prazo is not None
        pal = tema.atual
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 10)
        lay.setSpacing(6)

        topo = QHBoxLayout()
        topo.setSpacing(6)
        self.chk = QCheckBox()
        self.chk.setToolTip("Concluir")
        self.chk.setVisible(tarefa is not None and not tarefa.eh_nota)
        if tarefa is not None:
            self.chk.setChecked(tarefa.concluida)
        topo.addWidget(self.chk)
        self.btn_data = _plano("Data", "calendario")
        topo.addWidget(self.btn_data)
        topo.addStretch(1)
        self.btn_prio = _plano(icone="bandeira", dica="Prioridade")
        self.btn_prio.setFixedSize(30, 28)
        topo.addWidget(self.btn_prio)
        lay.addLayout(topo)
        if tarefa is not None:
            sep = QFrame()
            sep.setFixedHeight(1)
            sep.setStyleSheet(f"background: {pal.borda};")
            lay.addWidget(sep)

        linha_titulo = QHBoxLayout()
        self.titulo = QLineEdit(tarefa.titulo if tarefa else "")
        self.titulo.setObjectName("semBorda")
        self.titulo.setPlaceholderText("O que você gostaria de fazer?")
        self.titulo.setStyleSheet(f"font-size: {20 if acoplado else 14}px; font-weight: 700;")
        linha_titulo.addWidget(self.titulo, 1)
        self.btn_modo = _plano(icone="lista", dica="Alternar entre descrição e lista de itens")
        self.btn_modo.setCheckable(True)
        self.btn_modo.setFixedSize(28, 28)
        linha_titulo.addWidget(self.btn_modo)
        lay.addLayout(linha_titulo)

        self.notas = EditorDescricao(tarefa.notas if tarefa else "")
        self.notas.setObjectName("semBorda")
        if acoplado:
            self.notas.setMinimumHeight(120)
            self.notas.setStyleSheet("font-size: 14px;")
            lay.addWidget(self.notas, 1)
        else:
            self.notas.setFixedHeight(92)
            lay.addWidget(self.notas)

        self.caixa_itens = QWidget()
        self.lay_itens = QVBoxLayout(self.caixa_itens)
        self.lay_itens.setContentsMargins(0, 0, 0, 0)
        self.lay_itens.setSpacing(2)
        self.caixa_itens.setVisible(False)
        lay.addWidget(self.caixa_itens)
        self._itens: list[dict] = []
        if tarefa is not None and tarefa.id is not None:
            for s in self.servico.subtarefas(tarefa.id):
                self._novo_item(s.titulo, s.concluida, s.id)

        self.comentario = QLineEdit()
        self.comentario.setPlaceholderText("Escrever um comentário")
        self.comentario.setVisible(False)
        lay.addWidget(self.comentario)

        lay.addSpacing(6)
        rodape = QHBoxLayout()
        rodape.setSpacing(4)
        self.btn_lista = _plano("Caixa de Entrada", "caixa")
        rodape.addWidget(self.btn_lista)
        rodape.addStretch(1)
        self.rot_tags = QLabel("")
        self.rot_tags.setStyleSheet(f"color: {pal.apagado}; font-size: 11px;")
        rodape.addWidget(self.rot_tags)
        self.btn_comentario = _plano(icone="comentario", dica="Comentar")
        self.btn_comentario.setFixedSize(30, 28)
        self.btn_comentario.setVisible(tarefa is not None and tarefa.id is not None)
        rodape.addWidget(self.btn_comentario)
        self.btn_mais = _plano(icone="reticencias", dica="Mais")
        self.btn_mais.setFixedSize(30, 28)
        rodape.addWidget(self.btn_mais)
        lay.addLayout(rodape)

        self.titulo.textChanged.connect(self._ao_digitar_titulo)
        self.titulo.returnPressed.connect(self.notas.setFocus if acoplado else self.close)
        self.btn_data.clicked.connect(self.abrir_data)
        self.btn_prio.clicked.connect(self._menu_prioridade)
        self.btn_modo.toggled.connect(self._alternar_modo)
        self.btn_lista.clicked.connect(self.abrir_lista)
        self.btn_mais.clicked.connect(self._menu_mais)
        self.btn_comentario.clicked.connect(self._alternar_comentario)
        self.chk.toggled.connect(self._alternar_conclusao)
        self.comentario.returnPressed.connect(self._enviar_comentario)
        self._atualizar_chip()
        self._atualizar_prio()
        self._atualizar_lista()
        self._atualizar_tags()
        if tarefa is not None:
            self._ao_digitar_titulo(tarefa.titulo)
            if self._itens:
                self.btn_modo.setChecked(True)
        if acoplado:
            self.titulo.textChanged.connect(self._agendar_gravacao)
            self.notas.textChanged.connect(self._agendar_gravacao)

    # ---- aparência ----
    def _atualizar_chip(self):
        e = self.estado
        texto, tom = rotulo_prazo(e["prazo"], e["hora"], e["duracao_min"], e["inicio"], bool(e["repeticao"]))
        pal = tema.atual
        cor = {"atrasado": pal.vermelho, "hoje": pal.destaque, "normal": pal.destaque, "vazio": pal.apagado}[tom]
        self.btn_data.setText(texto)
        self.btn_data.setIcon(icones.icone("calendario", cor, 16))
        self.btn_data.setStyleSheet(f"color: {cor}; text-align: left; font-size: 12px;")

    def _atualizar_prio(self):
        pal = tema.atual
        cor = pal.prioridade[self.prio]
        self.btn_prio.setIcon(icones.icone("bandeira-cheia" if self.prio else "bandeira", cor, 18))

    def _atualizar_lista(self):
        nome, cor = "Caixa de Entrada", tema.atual.apagado
        if self.projeto_id is not None:
            p = self.servico.banco.obter_projeto(self.projeto_id)
            if p:
                nome = p.nome
        self.btn_lista.setText(nome)
        self.btn_lista.setIcon(icones.icone("caixa" if self.projeto_id is None else "lista", cor, 16))

    def _atualizar_tags(self):
        self.rot_tags.setText("  ".join(f"#{t}" for t in self.tags[:3]) + ("…" if len(self.tags) > 3 else ""))

    def _ao_digitar_titulo(self, texto: str):
        if not self.acoplado:
            self.adjustSize()

    def _alternar_comentario(self):
        self.comentario.setVisible(not self.comentario.isVisible())
        if self.comentario.isVisible():
            self.comentario.setFocus()
        if not self.acoplado:
            self.adjustSize()

    def _alternar_modo(self, lista: bool):
        self.caixa_itens.setVisible(lista)
        self.notas.setVisible(not lista)
        if lista and not self._itens:
            self._novo_item("", False, None, foco=True)
        if not self.acoplado:
            self.adjustSize()

    def _novo_item(self, texto: str = "", marcado: bool = False, id_: int | None = None, foco: bool = False,
                   depois_de: int | None = None):
        linha = QWidget()
        h = QHBoxLayout(linha)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        c = QCheckBox()
        c.setChecked(marcado)
        ed = QLineEdit(texto)
        ed.setObjectName("semBorda")
        ed.setPlaceholderText("Pressione 'Entrar' para adicionar item na lista")
        ed.setStyleSheet("font-size: 12px;")
        x = _plano(icone="fechar", dica="Remover item")
        x.setFixedSize(22, 22)
        h.addWidget(c)
        h.addWidget(ed, 1)
        h.addWidget(x)
        item = {"id": id_, "w": linha, "chk": c, "ed": ed, "removido": False, "feito0": marcado, "txt0": texto}
        idx = len(self._itens) if depois_de is None else depois_de + 1
        self._itens.insert(idx, item)
        self.lay_itens.insertWidget(idx, linha)
        ed.returnPressed.connect(lambda: self._novo_item("", False, None, foco=True,
                                                         depois_de=self._itens.index(item)))
        x.clicked.connect(lambda: self._remover_item(item))
        if foco:
            ed.setFocus()
        self.adjustSize()
        return item

    def _remover_item(self, item: dict):
        item["removido"] = True
        item["w"].setVisible(False)
        if not any(not i["removido"] for i in self._itens):
            self._novo_item("", False, None, foco=True)
        self.adjustSize()

    # ---- seletores ----
    def _estado_para_seletor(self) -> dict:
        return dict(self.estado)

    def abrir_data(self) -> SeletorData:
        sel = SeletorData(self._estado_para_seletor(), self, bool(self.janela.prefs.get("semana_comeca_segunda")))
        sel.aplicado.connect(self.definir_data)
        r = self.btn_data.rect()
        sel.mostrar_perto(self.btn_data.mapToGlobal(r.bottomLeft()))
        self.seletor_data = sel
        return sel

    def definir_data(self, estado: dict):
        self.estado = dict(estado)
        self.mod.add("data")
        self._atualizar_chip()
        self._agendar_gravacao()

    def _menu_prioridade(self):
        m = QMenu(self)
        for valor, nome in NOMES_PRIORIDADE:
            cor = tema.atual.prioridade[valor]
            a = m.addAction(icones.icone("bandeira-cheia" if valor else "bandeira", cor, 16),
                            nome + ("   ✓" if valor == self.prio else ""))
            a.triggered.connect(lambda _=False, v=valor: self.definir_prioridade(v))
        m.exec(self.btn_prio.mapToGlobal(self.btn_prio.rect().bottomLeft()))

    def definir_prioridade(self, valor: int):
        self.prio = valor
        self.mod.add("prio")
        self._atualizar_prio()
        self._agendar_gravacao()

    def abrir_lista(self) -> SeletorLista:
        sel = SeletorLista(self.servico.banco.listar_projetos(), self.projeto_id, self)
        sel.escolhida.connect(self.definir_lista)
        sel.mostrar_perto(self.btn_lista.mapToGlobal(self.btn_lista.rect().topLeft()) - QPoint(0, 0))
        self.seletor_lista = sel
        return sel

    def definir_lista(self, projeto_id):
        self.projeto_id = projeto_id
        self.mod.add("projeto")
        self._atualizar_lista()
        self._agendar_gravacao()

    def abrir_tags(self) -> SeletorTags:
        existentes = [t.nome for t in self.servico.banco.listar_tags()]
        sel = SeletorTags(existentes, self.tags, self)
        sel.escolhidas.connect(self.definir_tags)
        sel.mostrar_perto(self.btn_mais.mapToGlobal(self.btn_mais.rect().bottomLeft()))
        self.seletor_tags = sel
        return sel

    def definir_tags(self, tags: list[str]):
        self.tags = list(tags)
        self.mod.add("tags")
        self._atualizar_tags()
        self._agendar_gravacao()

    def _menu_mais(self):
        m = QMenu(self)
        m.addAction("Etiquetas", self.abrir_tags)
        sub = m.addMenu("Adicionar a partir do modelo")
        modelos = self.servico.modelos.listar()
        if modelos:
            for mo in modelos:
                sub.addAction(mo.nome, lambda _=False, u=mo.uuid: self._usar_modelo(u))
        else:
            sub.addAction("Nenhum modelo salvo").setEnabled(False)
        if self.t is not None and self.t.id is not None:
            j, tid, t = self.janela, self.t.id, self.t
            m.addSeparator()
            m.addAction("Desafixar" if t.fixada else "Fixar no topo", lambda: self._e_fechar(j.fixar_tarefa, tid))
            m.addAction("Duplicar", self._duplicar)
            m.addAction("Iniciar foco", lambda: self._e_fechar(j.iniciar_foco_na_tarefa, tid))
            m.addAction("Sugerir subtarefas com IA", lambda: self._e_fechar(j.sugerir_subtarefas, tid))
            m.addAction("Reabrir (não será feito)" if t.descartada else "Não será feito",
                        lambda: self._e_fechar(j.descartar_tarefa, tid))
            m.addAction("Salvar como modelo...", lambda: self._e_fechar(j.salvar_modelo, tid))
            m.addSeparator()
            m.addAction("Anexos, lembrete constante e mais (painel lateral)",
                        lambda: self._abrir_painel_lateral())
            m.addAction("Mover para a lixeira", self._apagar)
        m.exec(self.btn_mais.mapToGlobal(self.btn_mais.rect().bottomLeft()))

    def _e_fechar(self, acao, tarefa_id: int):
        """Grava o que foi digitado, fecha o cartão e roda a ação da janela."""
        self.close()
        acao(tarefa_id)

    def _abrir_painel_lateral(self):
        tid = self.t.id
        self.close()
        self.janela.definir_detalhe_lateral(True)
        self.janela.selecionar_tarefa(tid)

    def _usar_modelo(self, uuid: str):
        pid = self.projeto_id
        self._feito = True
        t = self.servico.modelos.criar_tarefa(uuid, projeto_id=pid)
        ini = self.estado.get("prazo")
        if self._prefill and ini and t.prazo is None:
            t.prazo, t.prazo_hora = ini, self.estado.get("hora")
            self.servico.salvar(t)
        self.salvou.emit(t)
        self.close()

    def _duplicar(self):
        self._feito = True
        self._gravar_edicao()
        novo = self.servico.duplicar(self.t.id)
        self.salvou.emit(novo)
        self.close()

    def _apagar(self):
        self._feito = True
        self.servico.apagar(self.t.id)
        self.salvou.emit(None)
        self.close()

    def _alternar_conclusao(self, marcado: bool):
        if self.t is not None and self.t.id is not None and marcado != self.t.concluida:
            self.t = self.servico.alternar_conclusao(self.t.id)
            self.mod.add("concluir")
            if self.acoplado:
                self.salvou.emit(self.t)

    def _enviar_comentario(self):
        texto = self.comentario.text().strip()
        if texto and self.t is not None and self.t.id is not None:
            self.servico.comentarios.adicionar(self.t.id, texto)
            self.comentario.clear()
            self.comentario.setPlaceholderText("Comentário adicionado")

    # ---- gravar ----
    def _aplicar_estado(self, t):
        e = self.estado
        t.prazo, t.prazo_hora, t.inicio = e["prazo"], e["hora"], e["inicio"]
        t.duracao_min = e["duracao_min"]
        t.lembretes = list(e["lembretes"])
        t.repeticao = e["repeticao"]

    def _itens_texto(self) -> list[dict]:
        return [i for i in self._itens if not i["removido"]]

    def _gravar_edicao(self):
        t = self.servico.banco.obter_tarefa(self.t.id) or self.t
        titulo = self.titulo.text().strip()
        if titulo:
            t.titulo = titulo
        if not self.btn_modo.isChecked() or True:
            t.notas = self.notas.toPlainText()
        self._aplicar_estado(t)
        t.prioridade = Prioridade(self.prio)
        t.tags = list(self.tags)
        t.projeto_id = self.projeto_id
        self.t = self.servico.salvar(t)
        self._gravar_itens(self.t)
        return self.t

    def _gravar_itens(self, pai):
        for i in self._itens:
            texto = i["ed"].text().strip()
            if i["id"] is None:
                if i["removido"] or not texto:
                    continue
                try:
                    novo = self.servico.adicionar_subtarefa(pai.id, texto)
                except ValueError:
                    continue
                if i["chk"].isChecked():
                    self.servico.alternar_conclusao(novo.id)
            else:
                if i["removido"]:
                    self.servico.apagar(i["id"])
                    continue
                s = self.servico.banco.obter_tarefa(i["id"])
                if s is None:
                    continue
                if texto and texto != s.titulo:
                    s.titulo = texto
                    self.servico.salvar(s)
                if i["chk"].isChecked() != s.concluida:
                    self.servico.alternar_conclusao(s.id)

    # ---- modo acoplado: grava sozinho, sem fechar ----
    @property
    def pendente(self) -> bool:
        return self.acoplado and self._tempo_gravar.isActive()

    def _agendar_gravacao(self, *_):
        if self.acoplado and not self._feito and self.t is not None and self.t.id is not None:
            self._tempo_gravar.start()

    def gravar_agora(self, emitir: bool = True):
        """Acoplado: grava as edições já (sem fechar). Devolve True se gravou algo."""
        if not self.acoplado or self._feito or self.t is None or self.t.id is None:
            return False
        self._tempo_gravar.stop()
        t = self._gravar_edicao()
        if emitir:
            self.salvou.emit(t)
        return True

    def gravar(self):
        """Grava e devolve a tarefa (ou None se o cartão estava vazio). Só roda uma vez."""
        if self.acoplado:
            return self.t if self.gravar_agora() else None
        if self._feito:
            return None
        self._feito = True
        if self.t is not None and self.t.id is not None:
            t = self._gravar_edicao()
        else:
            titulo = self.titulo.text().strip()
            if not titulo:
                return None
            t = self.servico.adicionar_rapido(titulo, projeto_id=self.projeto_id)
            if "projeto" in self.mod:
                t.projeto_id = self.projeto_id
            if "data" in self.mod:
                self._aplicar_estado(t)
            elif self._prefill and t.prazo is None:
                t.prazo, t.prazo_hora = self.estado["prazo"], self.estado["hora"]
                t.lembretes = list(self.estado["lembretes"])
            if "prio" in self.mod:
                t.prioridade = Prioridade(self.prio)
            if "tags" in self.mod:
                t.tags = list(self.tags)
            if self.notas.toPlainText().strip():
                t.notas = self.notas.toPlainText()
            t = self.servico.salvar(t)
            self._gravar_itens(t)
            self.t = t
        self.salvou.emit(t)
        return t

    def close(self):
        if self.acoplado:                 # fixo na lateral: fechar é só gravar (quem decide sumir é a janela)
            self.gravar_agora()
            return True
        return super().close()

    def closeEvent(self, e):
        if self.acoplado:
            self.gravar_agora(emitir=False)
            super().closeEvent(e)
            return
        if self._fecho_espurio():
            e.ignore()
            return
        self.gravar()
        super().closeEvent(e)

    def hideEvent(self, e):
        if self.acoplado:
            if self.pendente and self.gravar_agora(emitir=False):
                self.janela.pedir_atualizacao()
        else:
            self.gravar()
        super().hideEvent(e)
