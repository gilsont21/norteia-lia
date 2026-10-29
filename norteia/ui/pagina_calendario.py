"""Calendário: dia, semana, mês e agenda. Arrastar muda a data (e a hora); duplo clique cria tarefa."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea, QStackedWidget, QToolTip,
                               QVBoxLayout, QWidget)

from ..core import calendario as cal
from ..core.calendario import Ocorrencia
from . import icones, tema
from .popovers import CartaoTarefa
from .util import (DIAS_CURTOS, INICIAIS, MESES, com_alfa, dia_por_extenso, hora_texto, intervalo_por_extenso,
                   nome_do_mes, texto_sobre)

GUTTER = 56                 # coluna das horas
HORA_ALT = 52               # altura de uma hora na grade
MIN_ALT = HORA_ALT / 60
PASSO_MIN = 15              # a hora "gruda" de 15 em 15 minutos
CHIP_ALT = 18


def _fonte(base: QFont, px: int, negrito: bool = False, riscado: bool = False) -> QFont:
    f = QFont(base)
    f.setPixelSize(px)
    if negrito:
        f.setWeight(QFont.DemiBold)
    f.setStrikeOut(riscado)
    return f


def _dica(o: Ocorrencia) -> str:
    partes = [o.titulo]
    if o.hora:
        partes.append(f"{hora_texto(o.hora)}–{hora_texto(o.fim_hora)}" if o.duracao_min else hora_texto(o.hora))
    if o.varios_dias:
        partes.append(f"{o.inicio:%d/%m} a {o.fim:%d/%m}")
    if o.local:
        partes.append(o.local)
    if o.externo:
        partes.append("(calendário externo, somente leitura)")
    if o.virtual:
        partes.append("(repetição)")
    return "\n".join(partes)


def _chave(o: Ocorrencia):
    """Identifica a ocorrência entre redesenhos (os objetos são refeitos a cada atualização)."""
    return (o.tarefa.id if o.tarefa is not None and o.tarefa.id is not None else o.titulo, o.inicio)


def _cor_do_estado(cor: str, alfa: int, estado: str) -> QColor:
    """Passar o mouse deixa a cor um pouco mais clara; selecionado, bem mais clara e cheia."""
    if estado == "hover":
        return com_alfa(QColor(cor).lighter(115).name(), min(255, alfa + 40))
    if estado == "sel":
        return com_alfa(QColor(cor).lighter(128).name(), 255)
    return com_alfa(cor, alfa)


def _contorno_selecao(p: QPainter, r: QRectF, raio: float):
    p.setPen(QPen(QColor(255, 255, 255, 190), 1.6))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(r.adjusted(0.8, 0.8, -0.8, -0.8), raio, raio)


def _pintar_chip(p: QPainter, r: QRect, o: Ocorrencia, base: QFont, continua_antes=False, continua_depois=False,
                 fantasma=False, estado: str = ""):
    """Barrinha colorida com o título (usada no mês e na faixa de dia inteiro)."""
    cor = QColor(o.cor)
    alfa = 70 if (o.concluida or o.virtual) else 200
    if fantasma:
        alfa = 120
    p.setPen(Qt.NoPen)
    fundo = _cor_do_estado(o.cor, alfa, estado)
    p.setBrush(fundo)
    raio = 4
    p.drawRoundedRect(QRectF(r), raio, raio)
    if continua_antes:                       # lado reto onde a barra continua
        p.drawRect(QRectF(r.left(), r.top(), raio + 1, r.height()))
    if continua_depois:
        p.drawRect(QRectF(r.right() - raio, r.top(), raio + 1, r.height()))
    if o.externo:
        p.setPen(QPen(cor, 1, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5), raio, raio)
    if estado == "sel":
        _contorno_selecao(p, QRectF(r), raio)
    f = _fonte(base, 12, riscado=o.concluida)
    p.setFont(f)
    cor_txt = QColor(tema.atual.apagado) if (o.concluida or o.virtual) else texto_sobre(o.cor)
    # bolinha de tarefa (cheia com visto quando concluída)
    if r.width() > 40:
        p.setPen(QPen(cor_txt, 1.2))
        p.setBrush(Qt.NoBrush)
        bol = QRectF(r.left() + 6, r.center().y() - 3.5, 7, 7)
        p.drawEllipse(bol)
        if o.concluida:
            p.setBrush(cor_txt)
            p.drawEllipse(bol.adjusted(2, 2, -2, -2))
    x0 = 17 if r.width() > 40 else 6
    hora_txt = "" if (not o.hora or o.dia_inteiro) else hora_texto(o.hora)
    largura_hora = 0
    if hora_txt and r.width() > 110:
        fh = _fonte(base, 10)
        p.setFont(fh)
        largura_hora = QFontMetrics(fh).horizontalAdvance(hora_txt) + 6
        p.setPen(com_alfa(cor_txt.name(), 190))
        p.drawText(r.adjusted(0, 0, -5, 0), Qt.AlignVCenter | Qt.AlignRight, hora_txt)
    p.setFont(f)
    texto = o.titulo if (largura_hora or not hora_txt) else f"{hora_txt} {o.titulo}"
    p.setPen(cor_txt)
    p.drawText(r.adjusted(x0, 0, -4 - largura_hora, 0), Qt.AlignVCenter | Qt.AlignLeft,
               QFontMetrics(f).elidedText(texto, Qt.ElideRight, max(r.width() - x0 - 4 - largura_hora, 10)))


class VistaMes(QWidget):
    CAB = 28

    def __init__(self, pagina):
        super().__init__()
        self.pagina = pagina
        self.setMouseTracking(True)
        self.setMinimumHeight(420)
        self.ano = self.mes = 0
        self.dias: list[date] = []
        self.por_dia: dict[date, list[Ocorrencia]] = {}
        self.hoje = date.today()
        self.selecionado: date | None = None
        self.celulas: dict[date, QRect] = {}
        self.hits: list[tuple[QRect, Ocorrencia, date]] = []
        self._pressionado = None
        self._vazio = None
        self._arrasto = None             # (ocorrencia, dia de origem, posição atual)
        self._hover = None

    def _estado(self, o: Ocorrencia) -> str:
        k = _chave(o)
        return "sel" if k == self.pagina.sel else ("hover" if k == self._hover else "")

    def _marcar_hover(self, o: Ocorrencia | None):
        k = _chave(o) if o is not None else None
        if k != self._hover:
            self._hover = k
            self.update()

    def leaveEvent(self, _):
        self._marcar_hover(None)

    def definir(self, ano, mes, dias, por_dia, hoje):
        self.ano, self.mes, self.dias, self.por_dia, self.hoje = ano, mes, dias, por_dia, hoje
        self._calcular()
        self.update()

    def _linhas(self) -> int:
        if not self.dias:
            return 5
        if len(self.dias) != 42:
            return max(len(self.dias) // 7, 1)
        return 6 if self.dias[35].month == self.mes else 5

    def _calcular(self):
        self.celulas = {}
        if not self.dias:
            return
        linhas = self._linhas()
        w, h = self.width(), self.height() - self.CAB
        for i, d in enumerate(self.dias[:linhas * 7]):
            col, lin = i % 7, i // 7
            x0, x1 = round(col * w / 7), round((col + 1) * w / 7)
            y0, y1 = self.CAB + round(lin * h / linhas), self.CAB + round((lin + 1) * h / linhas)
            self.celulas[d] = QRect(x0, y0, x1 - x0, y1 - y0)

    def resizeEvent(self, e):
        self._calcular()
        super().resizeEvent(e)

    def paintEvent(self, _):
        pal = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self.hits = []
        base = self.font()
        w = self.width()
        # cabeçalho dos dias da semana
        p.setFont(_fonte(base, 12, True))
        p.setPen(QColor(pal.apagado))
        primeiro = self.dias[0].weekday() if self.dias else 6
        for col in range(7):
            nome = DIAS_CURTOS[(primeiro + col) % 7]
            p.drawText(QRect(round(col * w / 7), 0, round(w / 7), self.CAB), Qt.AlignCenter, nome)
        p.setPen(QPen(QColor(pal.borda), 1))
        p.drawLine(0, self.CAB, w, self.CAB)
        for d, r in self.celulas.items():
            self._pintar_celula(p, d, r, base)
        if self._arrasto is not None:
            o, _origem, pos = self._arrasto
            alvo = self._celula_em(pos)
            if alvo is not None:
                r = self.celulas[alvo]
                p.setPen(QPen(QColor(pal.destaque), 2))
                p.setBrush(Qt.NoBrush)
                p.drawRect(r.adjusted(1, 1, -1, -1))
            fantasma = QRect(pos.x() - 50, pos.y() - 9, 140, CHIP_ALT)
            _pintar_chip(p, fantasma, o, base, fantasma=True)
        p.end()

    def _pintar_celula(self, p: QPainter, d: date, r: QRect, base: QFont):
        pal = tema.atual
        do_mes = d.month == self.mes or self.mes == 0
        if d == self.selecionado:
            p.fillRect(r, com_alfa(pal.destaque, 28))
        elif d.weekday() >= 5 and do_mes:
            p.fillRect(r, QColor(255, 255, 255, 6))
        p.setPen(QPen(QColor(pal.borda), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
        # número do dia
        p.setFont(_fonte(base, 12, True))
        numero = QRect(r.left() + 6, r.top() + 4, 24, 20)
        if d == self.hoje:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal.destaque))
            p.drawEllipse(numero.center(), 11, 11)
            p.setPen(QColor(pal.sobre_destaque))
            p.drawText(numero, Qt.AlignCenter, str(d.day))
        else:
            p.setPen(QColor(pal.texto if do_mes else pal.apagado))
            if d.day == 1:
                p.drawText(QRect(r.left() + 6, r.top() + 4, r.width() - 10, 20), Qt.AlignVCenter | Qt.AlignLeft,
                           f"1 de {MESES[d.month - 1][:3]}")
            else:
                p.drawText(numero, Qt.AlignCenter, str(d.day))
        itens = self.por_dia.get(d, [])
        topo = r.top() + 28
        vagas = max(0, (r.bottom() - topo - 14) // (CHIP_ALT + 2))
        mostrar = itens if len(itens) <= vagas else itens[:max(vagas - 1, 0)]
        for i, o in enumerate(mostrar):
            chip = QRect(r.left() + 3, topo + i * (CHIP_ALT + 2), r.width() - 6, CHIP_ALT)
            _pintar_chip(p, chip, o, base, continua_antes=o.inicio < d, continua_depois=o.fim > d,
                         estado=self._estado(o))
            self.hits.append((chip, o, d))
        if len(mostrar) < len(itens):
            p.setFont(_fonte(base, 11))
            p.setPen(QColor(pal.apagado))
            p.drawText(QRect(r.left() + 8, topo + len(mostrar) * (CHIP_ALT + 2), r.width() - 12, CHIP_ALT),
                       Qt.AlignVCenter | Qt.AlignLeft, f"+{len(itens) - len(mostrar)} mais")

    # ---- mouse ----
    def _celula_em(self, pos: QPoint) -> date | None:
        for d, r in self.celulas.items():
            if r.contains(pos):
                return d
        return None

    def _chip_em(self, pos: QPoint):
        for r, o, d in reversed(self.hits):
            if r.contains(pos):
                return o, d
        return None

    def _alvo_global(self, r: QRect) -> QRect:
        return QRect(self.mapToGlobal(r.topLeft()), r.size())

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        achado = self._chip_em(pos)
        self._vazio = None
        if e.button() == Qt.RightButton and achado:
            self.pagina.menu(achado[0], e.globalPosition().toPoint())
            return
        if e.button() != Qt.LeftButton:
            return
        if achado:
            self._pressionado = (achado[0], achado[1], pos)
            self.pagina.selecionar(achado[0])
        else:
            self._pressionado = None
            self.selecionado = self._celula_em(pos)
            self._vazio = self.selecionado
            self.pagina.selecionar(None)
            self.update()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._pressionado is not None and e.buttons() & Qt.LeftButton:
            o, d, inicio = self._pressionado
            if o.editavel and (pos - inicio).manhattanLength() > 8:
                self._arrasto = (o, d, pos)
                self.setCursor(Qt.ClosedHandCursor)
                self.update()
            return
        achado = self._chip_em(pos)
        self._marcar_hover(achado[0] if achado else None)
        if achado:
            QToolTip.showText(e.globalPosition().toPoint(), _dica(achado[0]), self)
            self.setCursor(Qt.PointingHandCursor)
        else:
            QToolTip.hideText()
            self.unsetCursor()

    def mouseReleaseEvent(self, e):
        arrasto, self._arrasto = self._arrasto, None
        pressionado, self._pressionado = self._pressionado, None
        vazio, self._vazio = getattr(self, "_vazio", None), None
        self.unsetCursor()
        pos = e.position().toPoint()
        if arrasto is not None:
            o, origem, _ = arrasto
            alvo = self._celula_em(pos)
            if alvo is not None and alvo != origem:
                novo_inicio = alvo - (origem - o.inicio)
                self.pagina.mover(o.tarefa.id, novo_inicio)
        elif pressionado is not None and e.button() == Qt.LeftButton:
            o = pressionado[0]
            achado = self._chip_em(pos)
            if achado and _chave(achado[0]) == _chave(o):
                self.pagina.abrir_cartao(achado[0], self._alvo_global(achado_rect(self.hits, achado[0], achado[1])))
        elif vazio is not None and e.button() == Qt.LeftButton and vazio in self.celulas:
            self.pagina.abrir_cartao_novo(vazio, None, self._alvo_global(self.celulas[vazio]))
        self.update()

    def mouseDoubleClickEvent(self, e):
        self.mousePressEvent(e)


def achado_rect(hits, o, dia) -> QRect:
    for r, oc, d in hits:
        if oc is o and d == dia:
            return r
    return QRect()


class CabecalhoDias(QWidget):
    """Nomes dos dias e a faixa de "dia inteiro" (inclusive tarefas de vários dias)."""
    TOPO = 54

    def __init__(self, pagina):
        super().__init__()
        self.pagina = pagina
        self.setMouseTracking(True)
        self.dias: list[date] = []
        self.por_dia: dict[date, list[Ocorrencia]] = {}
        self.hoje = date.today()
        self.hits: list[tuple[QRect, Ocorrencia]] = []
        self.faixas: list[tuple[Ocorrencia, int]] = []
        self._pressionado = None
        self._vazio = None
        self._arrasto = None
        self._hover = None
        self.setFixedHeight(self.TOPO + CHIP_ALT + 8)

    def _estado(self, o: Ocorrencia) -> str:
        k = _chave(o)
        return "sel" if k == self.pagina.sel else ("hover" if k == self._hover else "")

    def _marcar_hover(self, o: Ocorrencia | None):
        k = _chave(o) if o is not None else None
        if k != self._hover:
            self._hover = k
            self.update()

    def leaveEvent(self, _):
        self._marcar_hover(None)

    def definir(self, dias, por_dia, hoje):
        self.dias, self.por_dia, self.hoje = dias, por_dia, hoje
        itens = {}
        for d in dias:
            for o in por_dia.get(d, []):
                if o.dia_inteiro or o.varios_dias:
                    itens[id(o)] = o
        lista = sorted(itens.values(), key=lambda o: (o.inicio, -(o.fim - o.inicio).days, o.titulo))
        ocupado: list[date] = []             # último dia ocupado em cada linha
        self.faixas = []
        for o in lista:
            ini = max(o.inicio, dias[0])
            linha = next((i for i, fim in enumerate(ocupado) if fim < ini), None)
            if linha is None:
                ocupado.append(min(o.fim, dias[-1]))
                linha = len(ocupado) - 1
            else:
                ocupado[linha] = min(o.fim, dias[-1])
            self.faixas.append((o, linha))
        linhas = min(max(len(ocupado), 1), 4)
        self.setFixedHeight(self.TOPO + linhas * (CHIP_ALT + 2) + 8)
        self.update()

    def _largura_dia(self) -> float:
        return (self.width() - GUTTER) / max(len(self.dias), 1)

    def _dia_em_x(self, x: float) -> date | None:
        if not self.dias or x < GUTTER:
            return None
        i = int((x - GUTTER) // self._largura_dia())
        return self.dias[i] if 0 <= i < len(self.dias) else None

    def paintEvent(self, _):
        pal = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        base = self.font()
        lw = self._largura_dia()
        p.setFont(_fonte(base, 11))
        p.setPen(QColor(pal.apagado))
        p.drawText(QRect(0, self.TOPO + 2, GUTTER - 6, 16), Qt.AlignRight | Qt.AlignVCenter, "dia todo")
        for i, d in enumerate(self.dias):
            x = GUTTER + i * lw
            ehoje = d == self.hoje
            p.setFont(_fonte(base, 11, True))
            p.setPen(QColor(pal.destaque if ehoje else pal.apagado))
            p.drawText(QRectF(x, 6, lw, 16), Qt.AlignCenter, DIAS_CURTOS[d.weekday()].upper())
            if ehoje:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(pal.destaque))
                p.drawEllipse(QPointF(x + lw / 2, 34), 14, 14)
            p.setFont(_fonte(base, 16, True))
            p.setPen(QColor(pal.sobre_destaque if ehoje else pal.texto))
            p.drawText(QRectF(x, 20, lw, 28), Qt.AlignCenter, str(d.day))
            p.setPen(QPen(QColor(pal.borda), 1))
            p.drawLine(int(x), self.TOPO - 6, int(x), self.height())
        p.setPen(QPen(QColor(pal.borda), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        self.hits = []
        ultimo = self.dias[-1] if self.dias else date.today()
        for o, linha in self.faixas:
            if linha >= 4:
                continue
            ini, fim = max(o.inicio, self.dias[0]), min(o.fim, ultimo)
            i0, i1 = self.dias.index(ini), self.dias.index(fim)
            r = QRect(int(GUTTER + i0 * lw) + 2, self.TOPO + linha * (CHIP_ALT + 2),
                      int((i1 - i0 + 1) * lw) - 4, CHIP_ALT)
            _pintar_chip(p, r, o, base, continua_antes=o.inicio < ini, continua_depois=o.fim > fim,
                         estado=self._estado(o))
            self.hits.append((r, o))
        if self._arrasto is not None:
            o, _dia, pos = self._arrasto
            _pintar_chip(p, QRect(pos.x() - 40, pos.y() - 9, 130, CHIP_ALT), o, base, fantasma=True)
        p.end()

    def _chip_em(self, pos):
        for r, o in reversed(self.hits):
            if r.contains(pos):
                return o
        return None

    def _alvo_global(self, r: QRect) -> QRect:
        return QRect(self.mapToGlobal(r.topLeft()), r.size())

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        o = self._chip_em(pos)
        self._vazio = None
        if e.button() == Qt.RightButton and o:
            self.pagina.menu(o, e.globalPosition().toPoint())
            return
        if e.button() != Qt.LeftButton:
            return
        if o:
            self._pressionado = (o, self._dia_em_x(pos.x()), pos)
            self.pagina.selecionar(o)
        else:
            self._pressionado = None
            self._vazio = self._dia_em_x(pos.x())
            self.pagina.selecionar(None)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._pressionado is not None and e.buttons() & Qt.LeftButton:
            o, dia, inicio = self._pressionado
            if o.editavel and (pos - inicio).manhattanLength() > 8:
                self._arrasto = (o, dia, pos)
                self.update()
            return
        o = self._chip_em(pos)
        self._marcar_hover(o)
        if o:
            QToolTip.showText(e.globalPosition().toPoint(), _dica(o), self)

    def mouseReleaseEvent(self, e):
        arrasto, self._arrasto = self._arrasto, None
        pressionado, self._pressionado = self._pressionado, None
        vazio, self._vazio = self._vazio, None
        pos = e.position().toPoint()
        if arrasto is not None:
            o, origem, _ = arrasto
            alvo = self._dia_em_x(pos.x())
            if alvo is not None and origem is not None and alvo != origem:
                self.pagina.mover(o.tarefa.id, alvo - (origem - o.inicio))
        elif pressionado is not None and e.button() == Qt.LeftButton:
            o = pressionado[0]
            atual = self._chip_em(pos)
            if atual is not None and _chave(atual) == _chave(o):
                r = next((r for r, oc in self.hits if oc is atual), QRect())
                self.pagina.abrir_cartao(atual, self._alvo_global(r))
        elif vazio is not None and e.button() == Qt.LeftButton:
            self.pagina.abrir_cartao_novo(vazio, None, QRect(self.mapToGlobal(pos), QSize(1, 1)))
        self.update()

    def mouseDoubleClickEvent(self, e):
        self.mousePressEvent(e)


class GradeHoras(QWidget):
    """Grade das 24 horas com os compromissos que têm hora marcada.

    Quando nada acontece de madrugada, as primeiras horas (00:00 até `h0`) ficam recolhidas numa faixa fina."""
    FAIXA = 30

    def __init__(self, pagina):
        super().__init__()
        self.pagina = pagina
        self.setMouseTracking(True)
        self.h0 = 0
        self.dias: list[date] = []
        self.por_dia: dict[date, list[Ocorrencia]] = {}
        self.hoje = date.today()
        self.agora = datetime.now()
        self.hits: list[tuple[QRect, Ocorrencia, date]] = []
        self._hover = None
        self._pressionado = None
        self._vazio = None
        self._acao = None                # ("mover"|"esticar", ocorrencia, dia, deslocamento_y, posição)
        self._ajustar_altura()

    def _topo(self) -> int:
        return self.FAIXA if self.h0 > 0 else 0

    def _ajustar_altura(self):
        self.setFixedHeight(self._topo() + (24 - self.h0) * HORA_ALT + 8)

    def definir(self, dias, por_dia, hoje, h0: int = 0):
        self.dias, self.por_dia, self.hoje, self.agora = dias, por_dia, hoje, datetime.now()
        if h0 != self.h0:
            self.h0 = h0
            self._ajustar_altura()
        self.update()

    def _lw(self) -> float:
        return (self.width() - GUTTER) / max(len(self.dias), 1)

    def _dia_em_x(self, x: float) -> date | None:
        if not self.dias or x < GUTTER:
            return None
        i = int((x - GUTTER) // self._lw())
        return self.dias[min(max(i, 0), len(self.dias) - 1)]

    def _min_em_y(self, y: float) -> int:
        return max(int((y - self._topo()) / MIN_ALT) + self.h0 * 60, self.h0 * 60)

    def _y_do_min(self, m: int) -> int:
        return self._topo() + int((m - self.h0 * 60) * MIN_ALT)

    @staticmethod
    def _gruda(m: float) -> int:
        return int(round(m / PASSO_MIN) * PASSO_MIN)

    RECUO_MIN = 12          # quanto um compromisso que começa depois fica recuado dentro do que já estava

    def _camadas(self, itens: list[Ocorrencia], largura: float) -> list[tuple[Ocorrencia, float, float, int]]:
        """[(ocorrência, esquerda, direita, camada)] relativos ao início da coluna do dia.

        Como no Google Agenda, compromissos que se cruzam ficam EM CIMA uns dos outros, não lado a lado:
        o que começa depois (ou é menor) fica por cima e levemente recuado; se começam juntos, o menor fica
        deslocado para a direita e o maior ganha uma folga na direita."""
        util = max(largura - 6, 20.0)
        base = 2.0
        # ordem: quem começa antes primeiro; no mesmo horário o mais longo primeiro (fica atrás)
        ordenados = sorted(itens, key=lambda o: (o.hora, -max(o.duracao_min, 20), o.titulo))
        info = []                           # (ocorrência, ini, fim, camada)
        grupo: list[int] = []
        fim_grupo = -1
        finais_por_camada: list[int] = []
        grupos: list[list[int]] = []
        for o in ordenados:
            ini = o.hora.hour * 60 + o.hora.minute
            fim = ini + max(o.duracao_min, 20)
            if ini >= fim_grupo:
                grupo, finais_por_camada, fim_grupo = [], [], ini
                grupos.append(grupo)
            camada = next((i for i, f in enumerate(finais_por_camada) if f <= ini), None)
            if camada is None:
                finais_por_camada.append(fim)
                camada = len(finais_por_camada) - 1
            else:
                finais_por_camada[camada] = fim
            info.append([o, ini, fim, camada, 0.0, base + util])
            grupo.append(len(info) - 1)
            fim_grupo = max(fim_grupo, fim)
        for g in grupos:
            for i in g:                     # esquerda de cada um depende do "pai" (cruza e está numa camada abaixo)
                o, ini, fim, camada, _e, _d = info[i]
                if camada == 0:
                    info[i][4] = base
                    continue
                pais = [info[j] for j in g if info[j][3] < camada and info[j][1] < fim and info[j][2] > ini]
                pai = max(pais, key=lambda x: x[3]) if pais else None
                if pai is None:
                    info[i][4] = base
                elif pai[1] == ini:         # começam juntos: o menor vai para o lado, sobre a metade direita
                    info[i][4] = pai[4] + (pai[5] - pai[4]) * 0.5
                    pai[5] = min(pai[5], base + util - max(util * 0.12, 8))
                else:                       # começou dentro do outro: recuo curto
                    info[i][4] = pai[4] + self.RECUO_MIN
            for i in g:
                info[i][4] = min(info[i][4], base + util - max(util * 0.3, 24))   # sempre sobra largura legível
        info.sort(key=lambda x: (x[3], x[1]))   # pintura: camadas de baixo primeiro
        return [(o, e, d, c) for o, _i, _f, c, e, d in info]

    def paintEvent(self, _):
        pal = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        base = self.font()
        lw = self._lw()
        w = self.width()
        topo = self._topo()
        self.hits = []
        # faixa recolhida (madrugada)
        if topo:
            p.fillRect(QRect(GUTTER, 0, w - GUTTER, topo), QColor(255, 255, 255, 5))
            p.setFont(_fonte(base, 9))
            p.setPen(QColor(pal.apagado))
            p.drawText(QRect(0, 0, GUTTER - 8, topo), Qt.AlignRight | Qt.AlignVCenter,
                       f"00:00\n- {self.h0:02d}:00")
        # linhas e rótulos das horas
        p.setFont(_fonte(base, 11))
        for h in range(self.h0, 24):
            y = topo + (h - self.h0) * HORA_ALT
            p.setPen(QPen(QColor(pal.borda), 1))
            p.drawLine(GUTTER, y, w, y)
            if h > self.h0 or topo:
                rot = "Meio-dia" if h == 12 else f"{h:02d}:00"
                if h > self.h0:
                    p.setPen(QColor(pal.apagado))
                    p.drawText(QRect(0, y - 8, GUTTER - 8, 16), Qt.AlignRight | Qt.AlignVCenter, rot)
        for i, d in enumerate(self.dias):
            x = int(GUTTER + i * lw)
            if d == self.hoje:
                p.fillRect(QRect(x, 0, int(lw), self.height()), com_alfa(pal.destaque, 12))
            p.setPen(QPen(QColor(pal.borda), 1))
            p.drawLine(x, 0, x, self.height())
        # compromissos com hora
        for i, d in enumerate(self.dias):
            x0 = GUTTER + i * lw
            itens = [o for o in self.por_dia.get(d, []) if not o.dia_inteiro and not o.varios_dias]
            for o, esq, dire, camada in self._camadas(itens, lw):
                self._pintar_evento(p, o, d, x0, esq, dire, camada, base)
        # linha do "agora"
        if self.hoje in self.dias:
            i = self.dias.index(self.hoje)
            minuto = self.agora.hour * 60 + self.agora.minute
            if minuto >= self.h0 * 60:
                y = self._y_do_min(minuto)
                p.setPen(QPen(QColor(pal.vermelho), 2))
                p.drawLine(int(GUTTER + i * lw), y, int(GUTTER + (i + 1) * lw), y)
                p.setBrush(QColor(pal.vermelho))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(GUTTER + i * lw, y), 4, 4)
                p.setFont(_fonte(base, 9))
                p.setPen(QColor(pal.vermelho))
                p.drawText(QRect(0, y - 8, GUTTER - 8, 16), Qt.AlignRight | Qt.AlignVCenter,
                           self.agora.strftime("%H:%M"))
        if self._acao is not None:
            self._pintar_fantasma(p, base)
        p.end()

    def _retangulo(self, o: Ocorrencia, x0: float, esq: float, dire: float) -> QRect:
        ini = max(o.hora.hour * 60 + o.hora.minute, self.h0 * 60)
        y = self._y_do_min(ini)
        h = max(int(max(o.duracao_min, 20) * MIN_ALT) - 2, 16)
        return QRect(int(x0 + esq), y + 1, int(dire - esq - 2), h)

    def _estado(self, o: Ocorrencia) -> str:
        k = _chave(o)
        return "sel" if k == self.pagina.sel else ("hover" if k == self._hover else "")

    def _marcar_hover(self, o: Ocorrencia | None):
        k = _chave(o) if o is not None else None
        if k != self._hover:
            self._hover = k
            self.update()

    def leaveEvent(self, _):
        self._marcar_hover(None)

    def _pintar_evento(self, p, o, d, x0, esq, dire, camada, base):
        pal = tema.atual
        r = self._retangulo(o, x0, esq, dire)
        alfa = 80 if (o.concluida or o.virtual) else 215
        estado = self._estado(o)
        p.setPen(Qt.NoPen)
        p.setBrush(_cor_do_estado(o.cor, alfa, estado))
        p.drawRoundedRect(QRectF(r), 5, 5)
        if camada > 0:                      # contorno na cor do fundo separa o que está por cima
            p.setPen(QPen(QColor(pal.fundo), 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(r), 5, 5)
        if o.externo:
            p.setPen(QPen(QColor(o.cor), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)
        if estado == "sel":
            _contorno_selecao(p, QRectF(r), 5)
        cor_txt = QColor(pal.apagado) if (o.concluida or o.virtual) else texto_sobre(o.cor)
        f = _fonte(base, 12, True, o.concluida)
        p.setFont(f)
        p.setPen(cor_txt)
        fm = QFontMetrics(f)
        p.drawText(r.adjusted(6, 3, -4, 0), Qt.AlignLeft | Qt.AlignTop, fm.elidedText(o.titulo, Qt.ElideRight, r.width() - 10))
        if r.height() >= 36:
            p.setFont(_fonte(base, 11, False))
            p.drawText(r.adjusted(6, 19, -4, 0), Qt.AlignLeft | Qt.AlignTop,
                       f"{hora_texto(o.hora)}–{hora_texto(o.fim_hora)}")
        self.hits.append((r, o, d))

    def _pintar_fantasma(self, p, base):
        pal = tema.atual
        acao, o, _dia, desloc, pos = self._acao
        d = self._dia_em_x(pos.x())
        if d is None:
            return
        i = self.dias.index(d)
        x0 = GUTTER + i * self._lw()
        if acao == "mover":
            ini = min(max(self._gruda(self._min_em_y(pos.y() - desloc)), 0), 24 * 60 - PASSO_MIN)
            dur = max(o.duracao_min, 20)
            titulo = f"{ini // 60:02d}:{ini % 60:02d}"
        else:
            ini = o.hora.hour * 60 + o.hora.minute
            fim = max(self._gruda(self._min_em_y(pos.y())), ini + PASSO_MIN)
            dur = fim - ini
            x0 = GUTTER + self.dias.index(_dia) * self._lw()
            titulo = f"{dur} min"
        r = QRect(int(x0 + 2), self._y_do_min(ini) + 1, int(self._lw() - 6), max(int(dur * MIN_ALT) - 2, 16))
        p.setPen(QPen(QColor(pal.destaque), 2))
        p.setBrush(com_alfa(o.cor, 110))
        p.drawRoundedRect(QRectF(r), 5, 5)
        p.setFont(_fonte(base, 12, True))
        p.setPen(QColor(pal.texto))
        p.drawText(r.adjusted(6, 3, -4, 0), Qt.AlignLeft | Qt.AlignTop, titulo)

    # ---- mouse ----
    def _evento_em(self, pos):
        for r, o, d in reversed(self.hits):
            if r.contains(pos):
                return r, o, d
        return None

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        achado = self._evento_em(pos)
        if e.button() == Qt.RightButton and achado:
            self.pagina.menu(achado[1], e.globalPosition().toPoint())
            return
        if e.button() != Qt.LeftButton:
            return
        self._vazio = None
        if achado:
            r, o, d = achado
            self._pressionado = (r, o, d, pos)
            self.pagina.selecionar(o)
        else:
            self._pressionado = None
            dia = self._dia_em_x(pos.x())
            if dia is not None:
                m = min(self._gruda(self._min_em_y(pos.y())), 24 * 60 - PASSO_MIN)
                self._vazio = (dia, time(m // 60, m % 60), pos)
            self.pagina.selecionar(None)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._pressionado is not None and e.buttons() & Qt.LeftButton:
            r, o, d, inicio = self._pressionado
            if o.editavel and (self._acao is not None or (pos - inicio).manhattanLength() > 6):
                borda = inicio.y() >= r.bottom() - 6
                if borda:
                    self._acao = ("esticar", o, d, 0, pos)
                    self.setCursor(Qt.SizeVerCursor)
                else:
                    self._acao = ("mover", o, d, inicio.y() - r.top(), pos)
                    self.setCursor(Qt.ClosedHandCursor)
                self.update()
            return
        achado = self._evento_em(pos)
        self._marcar_hover(achado[1] if achado else None)
        if achado:
            r, o, _ = achado
            self.setCursor(Qt.SizeVerCursor if (o.editavel and pos.y() >= r.bottom() - 6) else Qt.PointingHandCursor)
            QToolTip.showText(e.globalPosition().toPoint(), _dica(o), self)
        else:
            self.unsetCursor()
            QToolTip.hideText()

    def mouseReleaseEvent(self, e):
        acao, self._acao = self._acao, None
        pressionado, self._pressionado = self._pressionado, None
        vazio, self._vazio = self._vazio, None
        self.unsetCursor()
        pos = e.position().toPoint()
        if acao is not None:
            tipo, o, dia_origem, desloc, _ = acao
            if tipo == "mover":
                alvo = self._dia_em_x(pos.x())
                ini = min(max(self._gruda(self._min_em_y(pos.y() - desloc)), self.h0 * 60), 24 * 60 - PASSO_MIN)
                if alvo is not None:
                    novo_inicio = alvo - (dia_origem - o.inicio)
                    self.pagina.mover(o.tarefa.id, novo_inicio, time(ini // 60, ini % 60))
            else:
                inicio_min = o.hora.hour * 60 + o.hora.minute
                fim = max(self._gruda(self._min_em_y(pos.y())), inicio_min + PASSO_MIN)
                self.pagina.redimensionar(o.tarefa.id, fim - inicio_min)
        elif pressionado is not None and e.button() == Qt.LeftButton:
            r, o, d, _ = pressionado
            achado = self._evento_em(pos)
            if achado and _chave(achado[1]) == _chave(o):
                self.pagina.abrir_cartao(achado[1], QRect(self.mapToGlobal(achado[0].topLeft()), achado[0].size()))
        elif vazio is not None and e.button() == Qt.LeftButton:
            dia, hora, p0 = vazio
            self.pagina.abrir_cartao_novo(dia, hora, QRect(self.mapToGlobal(p0), QSize(1, 1)))
        self.update()

    def mouseDoubleClickEvent(self, e):
        self.mousePressEvent(e)


class VistaSemana(QWidget):
    """Semana (7 dias) ou dia (1 dia): cabeçalho fixo e grade de horas que rola."""

    def __init__(self, pagina, dias: int):
        super().__init__()
        self.n = dias
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.cabecalho = CabecalhoDias(pagina)
        self.grade = GradeHoras(pagina)
        self.rolagem = QScrollArea()
        self.rolagem.setWidgetResizable(True)
        self.rolagem.setFrameShape(QScrollArea.NoFrame)
        self.rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.rolagem.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.rolagem.setWidget(self.grade)
        self.rolagem.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget"
                                   " { background: transparent; }")
        self._ajuste = QWidget()
        h = QHBoxLayout(self._ajuste)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self.cabecalho, 1)
        self._espaco = QWidget()
        h.addWidget(self._espaco)
        lay.addWidget(self._ajuste)
        lay.addWidget(self.rolagem, 1)
        self._rolou = False
        self._h0 = -1

    def definir(self, dias, por_dia, hoje, recolher: bool = True):
        self._espaco.setFixedWidth(self.rolagem.verticalScrollBar().sizeHint().width())
        horas = [o.hora.hour for d in dias for o in por_dia.get(d, [])
                 if o.hora and not o.dia_inteiro and not o.varios_dias]
        h0 = 0
        if recolher:
            h0 = min(7, min(horas)) if horas else 7
        self.cabecalho.definir(dias, por_dia, hoje)
        self.grade.definir(dias, por_dia, hoje, h0)
        if not self._rolou or h0 != self._h0:
            self._rolou = True
            self._h0 = h0
            comeco = 0
            if h0 == 0:
                comeco = 7 * HORA_ALT
                if horas and min(horas) < 7:
                    comeco = max(min(horas) - 1, 0) * HORA_ALT
            self.rolagem.verticalScrollBar().setValue(comeco)


class CartaoAgenda(QFrame):
    """Cartão de um compromisso na agenda: faixa colorida à esquerda, horário em destaque e título."""

    def __init__(self, pagina, o: Ocorrencia):
        super().__init__()
        self.pagina, self.o = pagina, o
        pal = tema.atual
        self.setMaximumWidth(780)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.aplicar_estilo(_chave(o) == pagina.sel)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 7)
        lay.setSpacing(1)
        if o.varios_dias:
            quando = f"{o.inicio:%d/%m} a {o.fim:%d/%m}"
        elif o.dia_inteiro:
            quando = ""
        else:
            quando = f"{hora_texto(o.hora)} - {hora_texto(o.fim_hora)}" if o.duracao_min else hora_texto(o.hora)
        if quando:
            q = QLabel(quando)
            q.setStyleSheet(f"font-size: 10px; color: {o.cor if QColor(o.cor).lightness() > 90 else pal.destaque};")
            lay.addWidget(q)
        t = QLabel(o.titulo + ("   (repete)" if o.virtual else ""))
        f = t.font()
        f.setPixelSize(13)
        f.setStrikeOut(o.concluida)
        t.setFont(f)
        t.setStyleSheet(f"color: {pal.apagado if (o.concluida or o.virtual) else pal.texto};")
        lay.addWidget(t)

    def aplicar_estilo(self, selecionado: bool):
        o = self.o
        fundo = com_alfa(o.cor, 95 if selecionado else 38).name(QColor.HexArgb)
        hover = com_alfa(o.cor, 95 if selecionado else 66).name(QColor.HexArgb)
        borda = "1px solid rgba(255,255,255,170)" if selecionado else "1px solid transparent"
        self.setStyleSheet(f"CartaoAgenda {{ background: {fundo}; border: {borda}; border-left: 3px solid {o.cor}; "
                           f"border-radius: 4px; }} CartaoAgenda:hover {{ background: {hover}; }} "
                           f"CartaoAgenda QLabel {{ background: transparent; }}")

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.pagina.menu(self.o, e.globalPosition().toPoint())
        elif e.button() == Qt.LeftButton:
            self.pagina.selecionar(self.o)
            self.pagina.abrir_cartao(self.o, QRect(self.mapToGlobal(QPoint(0, 0)), self.size()))

    def mouseDoubleClickEvent(self, e):
        self.mousePressEvent(e)


class VistaAgenda(QScrollArea):
    """Lista cronológica: o número do dia à esquerda e os cartões dos compromissos ao lado."""

    def __init__(self, pagina):
        super().__init__()
        self.pagina = pagina
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget"
                           " { background: transparent; }")
        self.miolo = QWidget()
        self.lay = QVBoxLayout(self.miolo)
        self.lay.setContentsMargins(8, 8, 8, 20)
        self.lay.setSpacing(14)
        self.setWidget(self.miolo)
        self.cartoes: list[CartaoAgenda] = []

    def definir(self, grupos: list[tuple[date, list[Ocorrencia]]], hoje: date):
        pal = tema.atual
        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.cartoes = []
        if not grupos:
            vazio = QLabel("Nada marcado neste período.")
            vazio.setObjectName("mensagemVazia")
            self.lay.addWidget(vazio)
        for d, itens in grupos:
            linha = QWidget()
            h = QHBoxLayout(linha)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(14)
            cab = QWidget()
            cab.setFixedWidth(84)
            hc = QHBoxLayout(cab)
            hc.setContentsMargins(0, 2, 0, 0)
            hc.setSpacing(6)
            dia = QLabel(str(d.day))
            dia.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {pal.destaque if d == hoje else pal.texto};")
            sem = QLabel(DIAS_CURTOS[d.weekday()])
            sem.setStyleSheet(f"font-size: 11px; color: {pal.apagado};")
            dia.setAlignment(Qt.AlignTop | Qt.AlignRight)
            sem.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            hc.addWidget(dia)
            hc.addWidget(sem)
            hc.addStretch(1)
            h.addWidget(cab, 0, Qt.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(5)
            for o in itens:
                c = CartaoAgenda(self.pagina, o)
                self.cartoes.append(c)
                col.addWidget(c)
            h.addLayout(col, 1)
            h.addSpacing(max(0, 0))
            self.lay.addWidget(linha)
        self.lay.addStretch(1)


class VistaAno(QWidget):
    """Doze mini-calendários; os dias que têm tarefas ficam marcados. Clicar abre o dia."""

    def __init__(self, pagina):
        super().__init__()
        self.pagina = pagina
        self.setMouseTracking(True)
        self.setMinimumSize(700, 560)
        self.ano = date.today().year
        self.dias_com: dict[date, int] = {}
        self.hoje = date.today()
        self.segunda = False
        self.celulas: dict[date, QRect] = {}
        self._hover: date | None = None

    def definir(self, ano: int, por_dia: dict, hoje: date, segunda: bool):
        self.ano, self.hoje, self.segunda = ano, hoje, segunda
        self.dias_com = {d: len(v) for d, v in por_dia.items() if v}
        self.update()

    def paintEvent(self, _):
        pal = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        base = self.font()
        self.celulas = {}
        colunas, linhas = 4, 3
        mw, mh = self.width() / colunas, self.height() / linhas
        nomes = ["S", "T", "Q", "Q", "S", "S", "D"] if self.segunda else ["D", "S", "T", "Q", "Q", "S", "S"]
        for m in range(12):
            x0, y0 = (m % colunas) * mw + 14, (m // colunas) * mh + 8
            cw, ch = (mw - 28) / 7, (mh - 56) / 7
            p.setFont(_fonte(base, 13, True))
            p.setPen(QColor(pal.texto))
            p.drawText(QRectF(x0, y0, mw - 28, 24), Qt.AlignVCenter | Qt.AlignLeft, MESES[m])
            p.setFont(_fonte(base, 9))
            p.setPen(QColor(pal.apagado))
            for i, n in enumerate(nomes):
                p.drawText(QRectF(x0 + i * cw, y0 + 26, cw, ch), Qt.AlignCenter, n)
            primeiro = date(self.ano, m + 1, 1)
            deslocamento = primeiro.weekday() if self.segunda else (primeiro.weekday() + 1) % 7
            ini = primeiro - timedelta(days=deslocamento)
            for i in range(42):
                d = ini + timedelta(days=i)
                r = QRectF(x0 + (i % 7) * cw, y0 + 26 + (i // 7 + 1) * ch, cw, ch)
                if d.month != m + 1:
                    p.setPen(QColor(tema.atual.sutil))
                    p.setFont(_fonte(base, 10))
                    p.drawText(r, Qt.AlignCenter, str(d.day))
                    continue
                self.celulas[d] = r.toRect()
                if self.dias_com.get(d):
                    p.setPen(Qt.NoPen)
                    p.setBrush(com_alfa(pal.destaque, 150))
                    p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 4, 4)
                if d == self._hover:
                    p.setPen(QPen(QColor(pal.destaque), 1))
                    p.setBrush(Qt.NoBrush)
                    p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 4, 4)
                if d == self.hoje:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(pal.destaque))
                    p.drawEllipse(r.center(), 9, 9)
                    p.setPen(QColor(pal.sobre_destaque))
                else:
                    p.setPen(QColor(pal.texto))
                p.setFont(_fonte(base, 10, d == self.hoje))
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
            self.setCursor(Qt.PointingHandCursor if d else Qt.ArrowCursor)
            if d is not None:
                n = self.dias_com.get(d, 0)
                QToolTip.showText(e.globalPosition().toPoint(),
                                  f"{d:%d/%m/%Y}" + (f"  ·  {n} item(ns)" if n else ""), self)
            self.update()

    def mousePressEvent(self, e):
        d = self._dia_em(e.position().toPoint())
        if d is not None and e.button() == Qt.LeftButton:
            self.pagina.ir_para(d, "dia")


MODOS = [("dia", "Dia", "D/1"), ("semana", "Semana", "W/2"), ("mes", "Mês", "M/3"), ("ano", "Ano", "Y/4"),
         ("agenda", "Agenda", "A/5"), ("multidia", "Multi-Dia", "5 dias"), ("multisemana", "Multi-Semana", "2 semanas")]
NOME_MODO = {m[0]: m[1] for m in MODOS}
SEPARAR_ANTES = "multidia"


class PaginaCalendario(QWidget):
    def __init__(self, janela):
        super().__init__()
        self.janela = janela
        self.modo = "semana"
        self.ancora = date.today()
        self.mostrar_concluidas = True
        self.cartao = None
        self.sel = None                  # chave da ocorrência selecionada (fica mais clara que as outras)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 12)
        lay.setSpacing(10)

        barra = QHBoxLayout()
        barra.setSpacing(6)
        self.btn_ante = _botao_plano("seta-esq", "Anterior")
        self.btn_prox = _botao_plano("seta-dir", "Próximo")
        self.btn_hoje = QPushButton("Hoje")
        self.btn_hoje.setCursor(Qt.PointingHandCursor)
        self.btn_novo = _botao_plano("mais", "Nova tarefa")
        self.btn_menu = _botao_plano("reticencias", "Mais opções")
        self.btn_visao = QPushButton("Semana")
        self.btn_visao.setCursor(Qt.PointingHandCursor)
        self.btn_visao.setMinimumWidth(96)
        self.titulo = QLabel()
        self.titulo.setObjectName("titulo")
        barra.addWidget(self.titulo)
        barra.addStretch(1)
        barra.addWidget(self.btn_novo)
        barra.addWidget(self.btn_visao)
        barra.addSpacing(6)
        barra.addWidget(self.btn_ante)
        barra.addWidget(self.btn_hoje)
        barra.addWidget(self.btn_prox)
        barra.addSpacing(6)
        barra.addWidget(self.btn_menu)
        lay.addLayout(barra)

        self.pilha = QStackedWidget()
        self.v_dia = VistaSemana(self, 1)
        self.v_semana = VistaSemana(self, 7)
        self.v_multidia = VistaSemana(self, 5)
        self.v_mes = VistaMes(self)
        self.v_ano = VistaAno(self)
        self.rolagem_ano = QScrollArea()
        self.rolagem_ano.setWidgetResizable(True)
        self.rolagem_ano.setFrameShape(QScrollArea.NoFrame)
        self.rolagem_ano.setWidget(self.v_ano)
        self.rolagem_ano.setStyleSheet("QScrollArea { background: transparent; } "
                                       "QScrollArea > QWidget > QWidget { background: transparent; }")
        self.v_agenda = VistaAgenda(self)
        self.vistas = {"dia": self.v_dia, "semana": self.v_semana, "multidia": self.v_multidia,
                       "mes": self.v_mes, "multisemana": self.v_mes, "ano": self.rolagem_ano,
                       "agenda": self.v_agenda}
        for v in (self.v_dia, self.v_semana, self.v_multidia, self.v_mes, self.rolagem_ano, self.v_agenda):
            self.pilha.addWidget(v)
        lay.addWidget(self.pilha, 1)
        self.erro = QLabel("")
        self.erro.setObjectName("mensagemVazia")
        self.erro.setVisible(False)
        lay.addWidget(self.erro)

        self.btn_ante.clicked.connect(lambda: self.navegar(-1))
        self.btn_prox.clicked.connect(lambda: self.navegar(+1))
        self.btn_hoje.clicked.connect(self.ir_hoje)
        self.btn_novo.clicked.connect(self._novo_pelo_botao)
        self.btn_visao.clicked.connect(self._menu_visao)
        self.btn_menu.clicked.connect(self._menu_opcoes)
        self.relogio = QTimer(self)
        self.relogio.timeout.connect(self._tique)
        self.relogio.start(60_000)
        self.atalhos = []
        for tecla, modo in (("D", "dia"), ("W", "semana"), ("M", "mes"), ("Y", "ano"), ("A", "agenda"),
                            ("1", "dia"), ("2", "semana"), ("3", "mes"), ("4", "ano"), ("5", "agenda")):
            sc = QShortcut(QKeySequence(tecla), self, activated=lambda m=modo: self.definir_modo(m))
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            self.atalhos.append(sc)
        sc = QShortcut(QKeySequence("T"), self, activated=self.ir_hoje)
        sc.setContext(Qt.WidgetWithChildrenShortcut)
        self.atalhos.append(sc)

    # ---- estado ----
    def _segunda(self) -> bool:
        return bool(self.janela.prefs.get("semana_comeca_segunda", False))

    def _recolher(self) -> bool:
        return bool(self.janela.prefs.get("calendario_recolher_madrugada", True))

    def definir_modo(self, modo: str):
        if modo not in NOME_MODO:
            return
        self.modo = modo
        self.btn_visao.setText(NOME_MODO[modo])
        self.atualizar()

    def _menu_visao(self):
        m = QMenu(self)
        for chave, nome, dica in MODOS:
            if chave == SEPARAR_ANTES:
                m.addSeparator()
            a = m.addAction(f"{nome}\t{dica}")
            a.setCheckable(True)
            a.setChecked(chave == self.modo)
            a.triggered.connect(lambda _=False, c=chave: self.definir_modo(c))
        m.exec(self.btn_visao.mapToGlobal(self.btn_visao.rect().bottomLeft()))

    def _menu_opcoes(self):
        m = QMenu(self)
        a = m.addAction("Mostrar tarefas concluídas")
        a.setCheckable(True)
        a.setChecked(self.mostrar_concluidas)
        a.triggered.connect(self.alternar_concluidas)
        b = m.addAction("Recolher as horas da madrugada")
        b.setCheckable(True)
        b.setChecked(self._recolher())
        b.triggered.connect(lambda v: self._definir_pref("calendario_recolher_madrugada", bool(v)))
        c = m.addAction("A semana começa na segunda")
        c.setCheckable(True)
        c.setChecked(self._segunda())
        c.triggered.connect(lambda v: self._definir_pref("semana_comeca_segunda", bool(v)))
        m.addSeparator()
        m.addAction("Integrações (Google Calendar)...", self.janela.abrir_integracoes)
        m.exec(self.btn_menu.mapToGlobal(self.btn_menu.rect().bottomLeft()))

    def alternar_concluidas(self, ligado: bool | None = None):
        self.mostrar_concluidas = (not self.mostrar_concluidas) if ligado is None else bool(ligado)
        self.atualizar()

    def _definir_pref(self, chave: str, valor):
        self.janela.aplicar_preferencias({chave: valor})
        self.atualizar()

    def ir_hoje(self):
        self.ancora = date.today()
        self.atualizar()

    def ir_para(self, dia: date, modo: str | None = None):
        self.ancora = dia
        if modo:
            self.definir_modo(modo)
        else:
            self.atualizar()

    def navegar(self, passo: int):
        a = self.ancora
        if self.modo == "dia":
            a += timedelta(days=passo)
        elif self.modo == "semana":
            a += timedelta(days=7 * passo)
        elif self.modo == "multidia":
            a += timedelta(days=5 * passo)
        elif self.modo == "multisemana":
            a += timedelta(days=14 * passo)
        elif self.modo == "mes":
            m = a.month - 1 + passo
            ano, mes = a.year + m // 12, m % 12 + 1
            a = date(ano, mes, min(a.day, 28))
        elif self.modo == "ano":
            a = date(a.year + passo, a.month, min(a.day, 28))
        else:
            a += timedelta(days=30 * passo)
        self.ancora = a
        self.atualizar()

    def periodo(self) -> tuple[date, date]:
        a = self.ancora
        if self.modo == "dia":
            return a, a
        if self.modo == "semana":
            ini = cal.inicio_da_semana(a, self._segunda())
            return ini, ini + timedelta(days=6)
        if self.modo == "multidia":
            return a, a + timedelta(days=4)
        if self.modo == "multisemana":
            ini = cal.inicio_da_semana(a, self._segunda())
            return ini, ini + timedelta(days=13)
        if self.modo == "mes":
            grade = cal.grade_do_mes(a.year, a.month, self._segunda())
            return grade[0], grade[-1]
        if self.modo == "ano":
            return date(a.year, 1, 1), date(a.year, 12, 31)
        return a, a + timedelta(days=59)

    def _tique(self):
        if self.isVisible():
            for v in (self.v_semana, self.v_dia, self.v_multidia):
                v.grade.agora = datetime.now()
                v.grade.update()

    # ---- desenho ----
    def atualizar(self):
        servico = self.janela.servico
        ini, fim = self.periodo()
        hoje = date.today()
        calend = servico.calendario
        com_concluidas = self.mostrar_concluidas
        a = self.ancora
        if self.modo == "ano":
            self.titulo.setText(str(a.year))
        else:
            self.titulo.setText(nome_do_mes(a))
        if self.modo == "mes":
            por_dia = calend.por_dia(ini, fim, incluir_finalizadas=com_concluidas)
            self.v_mes.definir(a.year, a.month, [ini + timedelta(days=i) for i in range(42)], por_dia, hoje)
        elif self.modo == "multisemana":
            por_dia = calend.por_dia(ini, fim, incluir_finalizadas=com_concluidas)
            self.v_mes.definir(a.year, 0, [ini + timedelta(days=i) for i in range(14)], por_dia, hoje)
        elif self.modo in ("semana", "dia", "multidia"):
            dias = [ini + timedelta(days=i) for i in range((fim - ini).days + 1)]
            por_dia = calend.por_dia(ini, fim, incluir_finalizadas=com_concluidas)
            self.vistas[self.modo].definir(dias, por_dia, hoje, self._recolher())
        elif self.modo == "ano":
            por_dia = calend.por_dia(ini, fim, incluir_finalizadas=com_concluidas)
            self.v_ano.definir(a.year, por_dia, hoje, self._segunda())
        else:
            grupos = calend.agenda(ini, 60, incluir_finalizadas=com_concluidas)
            self.v_agenda.definir(grupos, hoje)
        self.pilha.setCurrentWidget(self.vistas[self.modo])
        falhas = [f"{x['nome']}: {x['erro']}" for x in servico.assinaturas() if x.get("erro")]
        self.erro.setVisible(bool(falhas))
        self.erro.setText("  ·  ".join(falhas))

    # ---- chamadas das vistas ----
    def _repintar(self):
        for v in (self.v_mes, self.v_semana, self.v_dia, self.v_multidia):
            for w in v.findChildren(QWidget) + [v]:
                if isinstance(w, (VistaMes, CabecalhoDias, GradeHoras)):
                    w.update()
        for c in self.v_agenda.findChildren(CartaoAgenda):
            c.aplicar_estilo(_chave(c.o) == self.sel)

    def selecionar(self, o: Ocorrencia | None):
        self.sel = _chave(o) if o is not None else None
        self._repintar()
        if o is not None and o.tarefa is not None:
            self.janela.selecionar_tarefa(o.tarefa.id)
        else:
            self.janela.selecionar_tarefa(None)

    def mover(self, tarefa_id: int, dia: date, hora=cal._MANTER):
        cal.mover_para(self.janela.servico, tarefa_id, dia, hora)
        self.janela.atualizar(manter_selecao=True)

    def redimensionar(self, tarefa_id: int, minutos: int):
        cal.definir_duracao(self.janela.servico, tarefa_id, minutos)
        self.janela.atualizar(manter_selecao=True)

    def nova_em(self, dia: date, hora: time | None):
        self.abrir_cartao_novo(dia, hora, None)

    def _novo_pelo_botao(self):
        dia = self.ancora if self.modo == "dia" else date.today()
        alvo = QRect(self.btn_novo.mapToGlobal(self.btn_novo.rect().bottomLeft()), QSize(1, 1))
        self.abrir_cartao_novo(dia, None, alvo)

    def criar_em(self, texto: str, dia: date, hora: time | None):
        t = self.janela.servico.adicionar_rapido(texto)
        t.prazo, t.prazo_hora = dia, hora
        if hora is not None and not t.lembretes:
            t.lembretes = [0]
        self.janela.servico.salvar(t)
        self.janela.atualizar(selecionar_id=t.id)

    def abrir_cartao_novo(self, dia: date, hora: time | None, alvo: QRect | None = None) -> CartaoTarefa:
        c = CartaoTarefa(self.janela, prazo=dia, hora=hora)
        return self._mostrar_cartao(c, alvo)

    def abrir_cartao(self, o: Ocorrencia, alvo: QRect | None = None) -> CartaoTarefa | None:
        if o.tarefa is None or o.tarefa.id is None:
            return None
        t = self.janela.servico.banco.obter_tarefa(o.tarefa.id)
        if t is None:
            return None
        return self._mostrar_cartao(CartaoTarefa(self.janela, tarefa=t), alvo)

    def _mostrar_cartao(self, c: CartaoTarefa, alvo: QRect | None) -> CartaoTarefa:
        c.salvou.connect(self._cartao_salvo)
        self.cartao = c
        c.mostrar_perto(QCursor.pos(), alvo)
        c.titulo.setFocus()
        return c

    def _cartao_salvo(self, t):
        self.janela.atualizar(selecionar_id=t.id if t is not None else None, manter_selecao=t is None)

    def menu(self, o: Ocorrencia, pos_global: QPoint):
        self.janela.menu_da_tarefa_id(o.tarefa.id if o.tarefa else None, pos_global, externo=o)


def _botao_plano(icone: str, dica: str) -> QPushButton:
    b = QPushButton()
    b.setObjectName("btnIcone")
    b.setIcon(icones.icone(icone, tema.atual.texto, 18))
    b.setIconSize(QSize(18, 18))
    b.setFixedSize(32, 32)
    b.setToolTip(dica)
    b.setCursor(Qt.PointingHandCursor)
    return b
