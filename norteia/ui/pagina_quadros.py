"""Telas em quadro: Kanban, linha do tempo e Matriz de Eisenhower."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QMenu, QMessageBox, QPushButton, QScrollArea, QToolTip, QVBoxLayout, QWidget)

from ..core import calendario as cal
from ..core import kanban, matriz
from ..core.kanban import MODOS as MODOS_KANBAN
from . import tema
from .cartoes import ListaCartoes
from .delegados import PAPEL_TAREFA
from .util import DIAS_CURTOS, INICIAIS, MESES, com_alfa, texto_sobre


def _fonte(base: QFont, px: int, negrito=False) -> QFont:
    f = QFont(base)
    f.setPixelSize(px)
    if negrito:
        f.setWeight(QFont.DemiBold)
    return f


def _preparar_lista(lista: ListaCartoes, janela) -> None:
    servico = janela.servico
    lista.delegado.projetos = {p.id: p for p in servico.banco.listar_projetos()}
    lista.delegado.cores_tags = {g.nome: g.cor for g in servico.banco.listar_tags() if g.cor != "#8a8f98"}


# ============================================================ Kanban
class ColunaKanban(QFrame):
    LARGURA = 280

    def __init__(self, vista: "VistaKanban", coluna: kanban.Coluna, modo: str, projeto_id):
        super().__init__()
        self.vista, self.coluna, self.modo, self.projeto_id = vista, coluna, modo, projeto_id
        pal = tema.atual
        self.setObjectName("colunaKanban")
        self.setFixedWidth(self.LARGURA)
        self.setStyleSheet(f"QFrame#colunaKanban {{ background: {pal.barra}; border-radius: 10px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 10, 8, 8)
        lay.setSpacing(6)
        cab = QHBoxLayout()
        cab.setContentsMargins(6, 0, 2, 0)
        self.titulo = QLabel(coluna.titulo)
        self.titulo.setStyleSheet("font-weight: 600; font-size: 14px; background: transparent;")
        self.contagem = QLabel(str(len(coluna.tarefas)))
        self.contagem.setStyleSheet(f"color: {pal.apagado}; background: transparent;")
        cab.addWidget(self.titulo, 1)
        cab.addWidget(self.contagem)
        self.menu_btn = None
        if modo == "secao" and coluna.chave != "":
            self.menu_btn = QPushButton("⋯")
            self.menu_btn.setObjectName("btnIcone")
            self.menu_btn.setFixedSize(26, 26)
            self.menu_btn.setCursor(Qt.PointingHandCursor)
            self.menu_btn.clicked.connect(self._menu)
            cab.addWidget(self.menu_btn)
        lay.addLayout(cab)
        self.lista = ListaCartoes(coluna.chave)
        self.lista.preencher(coluna.tarefas)
        _preparar_lista(self.lista, vista.janela)
        lay.addWidget(self.lista, 1)
        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("+  Adicionar tarefa")
        self.entrada.setStyleSheet(f"QLineEdit {{ background: {pal.campo}; border: 1px solid transparent; "
                                   f"border-radius: 6px; padding: 8px 10px; }} QLineEdit:focus "
                                   f"{{ border: 1px solid {pal.destaque}; }}")
        self.entrada.setEnabled(coluna.aceita_soltar and coluna.chave != "atrasadas")
        lay.addWidget(self.entrada)
        self.lista.currentItemChanged.connect(lambda atual, _a: vista.selecionou(self, atual))
        self.lista.soltou.connect(vista.soltou)
        self.lista.alternou.connect(vista.alternar)
        self.lista.clicou_tarefa.connect(vista.janela.abrir_cartao_da_tarefa)
        self.lista.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(self._menu_cartao)
        self.entrada.returnPressed.connect(lambda: vista.nova(self.entrada, self.coluna.chave))

    def _menu(self):
        m = QMenu(self)
        m.addAction("Renomear...", lambda: self.vista.renomear_secao(self.coluna.chave))
        m.addAction("Mover para a esquerda", lambda: self.vista.mover_secao(self.coluna.chave, -1))
        m.addAction("Mover para a direita", lambda: self.vista.mover_secao(self.coluna.chave, +1))
        m.addSeparator()
        m.addAction("Apagar seção (as tarefas ficam sem seção)", lambda: self.vista.apagar_secao(self.coluna.chave))
        m.exec(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomLeft()))

    def _menu_cartao(self, pos):
        item = self.lista.itemAt(pos)
        t = self.lista.tarefa_do_item(item)
        if t is not None:
            self.lista.setCurrentItem(item)
            self.vista.janela.menu_da_tarefa_id(t.id, self.lista.mapToGlobal(pos))


class VistaKanban(QWidget):
    def __init__(self, janela):
        super().__init__()
        self.janela = janela
        self.modo = "secao"
        self.colunas_w: list[ColunaKanban] = []
        self._selecionada: int | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        barra = QHBoxLayout()
        barra.addWidget(QLabel("Agrupar por"))
        self.combo = QComboBox()
        for chave, nome in MODOS_KANBAN:
            self.combo.addItem(nome, chave)
        self.combo.setMinimumWidth(130)
        barra.addWidget(self.combo)
        self.btn_secao = QPushButton("+  Nova seção")
        self.btn_secao.setCursor(Qt.PointingHandCursor)
        barra.addWidget(self.btn_secao)
        barra.addStretch(1)
        lay.addLayout(barra)
        self.rolagem = QScrollArea()
        self.rolagem.setWidgetResizable(True)
        self.rolagem.setFrameShape(QScrollArea.NoFrame)
        self.rolagem.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.rolagem.setStyleSheet("QScrollArea { background: transparent; }")
        self.miolo = QWidget()
        self.miolo.setStyleSheet("background: transparent;")
        self.linha = QHBoxLayout(self.miolo)
        self.linha.setContentsMargins(0, 0, 0, 4)
        self.linha.setSpacing(12)
        self.rolagem.setWidget(self.miolo)
        lay.addWidget(self.rolagem, 1)
        self.combo.currentIndexChanged.connect(self._trocou_modo)
        self.btn_secao.clicked.connect(self.criar_secao)
        self._tarefas: list = []

    # ---- dados ----
    @property
    def projeto_id(self):
        return kanban.projeto_da_lista(self.janela.lista_atual)

    def modo_efetivo(self) -> str:
        return kanban.modo_valido(self.modo, self.janela.lista_atual)

    def _trocou_modo(self, _):
        self.modo = self.combo.currentData()
        self.carregar(self._tarefas)

    def carregar(self, tarefas: list):
        self._tarefas = tarefas
        modo = self.modo_efetivo()
        self.combo.blockSignals(True)
        self.combo.setCurrentIndex(self.combo.findData(modo))
        self.combo.blockSignals(False)
        self.btn_secao.setVisible(modo == "secao")
        while self.linha.count():
            w = self.linha.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.colunas_w = []
        for c in kanban.colunas(self.janela.servico, modo, tarefas, self.projeto_id):
            w = ColunaKanban(self, c, modo, self.projeto_id)
            self.linha.addWidget(w)
            self.colunas_w.append(w)
        self.linha.addStretch(1)
        self.miolo.setMinimumWidth(len(self.colunas_w) * (ColunaKanban.LARGURA + 12) + 4)
        if self._selecionada is not None:
            for w in self.colunas_w:
                w.lista.selecionar_id(self._selecionada)

    # ---- ações ----
    def selecionou(self, coluna: ColunaKanban, item):
        t = coluna.lista.tarefa_do_item(item)
        if t is None:
            return
        self._selecionada = t.id
        for w in self.colunas_w:
            if w is not coluna:
                w.lista.selecionar_id(None)
        self.janela.selecionar_tarefa(t.id)

    def soltou(self, tarefa_id: int, chave):
        try:
            kanban.mover(self.janela.servico, tarefa_id, self.modo_efetivo(), chave)
        except ValueError:
            return
        self._selecionada = tarefa_id
        self.janela.atualizar(manter_selecao=True)

    def alternar(self, tarefa_id: int):
        self.janela.alternar(tarefa_id)

    def nova(self, campo: QLineEdit, chave):
        texto = campo.text().strip()
        if not texto:
            return
        svc = self.janela.servico
        lista = self.janela.lista_atual
        modo = self.modo_efetivo()
        t = svc.adicionar_rapido(texto, projeto_id=kanban.projeto_da_lista(lista))
        if modo == "secao":
            t.secao = chave or ""
        elif modo == "prioridade":
            t.prioridade = type(t.prioridade)(int(chave))
        elif modo == "projeto":
            t.projeto_id = chave
        elif modo == "data" and t.prazo is None and chave not in ("sem", "atrasadas"):
            hoje = date.today()
            t.prazo = {"hoje": hoje, "amanha": hoje + timedelta(days=1), "semana": hoje + timedelta(days=7),
                       "depois": hoje + timedelta(days=30)}[chave]
        svc.salvar(t)
        campo.clear()
        self._selecionada = t.id
        self.janela.atualizar(selecionar_id=t.id)

    def criar_secao(self):
        nome, ok = QInputDialog.getText(self, "Nova seção", "Nome da seção:")
        if ok and nome.strip():
            kanban.criar_secao(self.janela.servico, self.projeto_id, nome)
            self.janela.atualizar(manter_selecao=True)

    def renomear_secao(self, nome: str, novo: str | None = None):
        if novo is None:
            novo, ok = QInputDialog.getText(self, "Renomear seção", "Novo nome:", text=nome)
            if not ok:
                return
        if novo.strip():
            kanban.renomear_secao(self.janela.servico, self.projeto_id, nome, novo)
            self.janela.atualizar(manter_selecao=True)

    def mover_secao(self, nome: str, passo: int):
        kanban.mover_secao(self.janela.servico, self.projeto_id, nome, passo)
        self.janela.atualizar(manter_selecao=True)

    def apagar_secao(self, nome: str):
        kanban.apagar_secao(self.janela.servico, self.projeto_id, nome)
        self.janela.atualizar(manter_selecao=True)


# ============================================================ Linha do tempo
ESQ = 230
LINHA_ALT = 34


class CabecalhoTempo(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(52)
        self.ini = date.today()
        self.n = 28
        self.hoje = date.today()

    def definir(self, ini: date, n: int, hoje: date):
        self.ini, self.n, self.hoje = ini, n, hoje
        self.update()

    def paintEvent(self, _):
        pal = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        base = self.font()
        dw = (self.width() - ESQ) / self.n
        for i in range(self.n):
            d = self.ini + timedelta(days=i)
            x = ESQ + i * dw
            if d.day == 1 or i == 0:
                p.setFont(_fonte(base, 12, True))
                p.setPen(QColor(pal.texto))
                p.drawText(QRectF(x + 4, 2, dw * 12, 20), Qt.AlignLeft | Qt.AlignVCenter,
                           f"{MESES[d.month - 1]} {d.year}")
            ehoje = d == self.hoje
            if ehoje:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(pal.destaque))
                p.drawRoundedRect(QRectF(x + 2, 24, dw - 4, 26), 6, 6)
            p.setFont(_fonte(base, 10))
            p.setPen(QColor(pal.sobre_destaque if ehoje else pal.apagado))
            p.drawText(QRectF(x, 24, dw, 12), Qt.AlignCenter, INICIAIS[d.weekday()])
            p.setFont(_fonte(base, 11, True))
            p.setPen(QColor(pal.sobre_destaque if ehoje else pal.texto))
            p.drawText(QRectF(x, 35, dw, 14), Qt.AlignCenter, str(d.day))
        p.setPen(QPen(QColor(pal.borda), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()


class QuadroTempo(QWidget):
    def __init__(self, vista: "VistaLinhaTempo"):
        super().__init__()
        self.vista = vista
        self.setMouseTracking(True)
        self.linhas: list = []          # tarefas na ordem das linhas
        self.ini = date.today()
        self.n = 28
        self.hoje = date.today()
        self.cores: dict = {}
        self.barras: list[tuple[QRect, object]] = []
        self.selecionada: int | None = None
        self._pressionada = None
        self._arrasto = None            # (modo, tarefa, delta_dias)

    def definir(self, linhas, ini, n, hoje, cores):
        self.linhas, self.ini, self.n, self.hoje, self.cores = linhas, ini, n, hoje, cores
        self.setMinimumHeight(max(len(linhas), 1) * LINHA_ALT + 8)
        self.update()

    def _dw(self) -> float:
        return (self.width() - ESQ) / self.n

    def _dia_em_x(self, x: float) -> date:
        i = int((x - ESQ) // self._dw())
        return self.ini + timedelta(days=min(max(i, 0), self.n - 1))

    @staticmethod
    def _periodo(t):
        return (t.inicio or t.prazo), t.prazo

    def _retangulo(self, t, i: int, delta_ini=0, delta_fim=0):
        a, b = self._periodo(t)
        if a is None:
            return None
        a, b = a + timedelta(days=delta_ini), b + timedelta(days=delta_fim)
        dw = self._dw()
        x0 = ESQ + (a - self.ini).days * dw
        x1 = ESQ + ((b - self.ini).days + 1) * dw
        return QRect(int(max(x0, ESQ)), i * LINHA_ALT + 6, int(max(min(x1, self.width()) - max(x0, ESQ), 0)),
                     LINHA_ALT - 12), x0, x1

    def paintEvent(self, _):
        pal = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        base = self.font()
        dw = self._dw()
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(pal.fundo))
        self.barras = []
        for i in range(self.n):
            d = self.ini + timedelta(days=i)
            x = ESQ + i * dw
            if d.weekday() >= 5:
                p.fillRect(QRectF(x, 0, dw, h), QColor(255, 255, 255, 7))
            if d == self.hoje:
                p.fillRect(QRectF(x, 0, dw, h), com_alfa(pal.destaque, 18))
            p.setPen(QPen(QColor(pal.borda), 1))
            p.drawLine(int(x), 0, int(x), h)
        for i, t in enumerate(self.linhas):
            y = i * LINHA_ALT
            if t.id == self.selecionada:
                p.fillRect(QRect(0, y, w, LINHA_ALT), QColor(pal.linha_selecionada))
            p.setPen(QPen(QColor(pal.borda), 1))
            p.drawLine(0, y + LINHA_ALT, w, y + LINHA_ALT)
            cor = self.cores.get(t.projeto_id, "#4772fa")
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(cor))
            p.drawEllipse(QPointF(16, y + LINHA_ALT / 2), 4, 4)
            f = _fonte(base, 13)
            p.setFont(f)
            p.setPen(QColor(pal.texto))
            p.drawText(QRect(28, y, ESQ - 36, LINHA_ALT), Qt.AlignVCenter | Qt.AlignLeft,
                       QFontMetrics(f).elidedText(t.titulo, Qt.ElideRight, ESQ - 40))
            self._pintar_barra(p, t, i, cor, base)
        p.setPen(QPen(QColor(pal.borda), 1))
        p.drawLine(ESQ, 0, ESQ, h)
        if self.hoje >= self.ini and (self.hoje - self.ini).days < self.n:
            x = ESQ + ((self.hoje - self.ini).days + 0.5) * dw
            p.setPen(QPen(QColor(pal.vermelho), 1.5))
            p.drawLine(int(x), 0, int(x), h)
        if not self.linhas:
            p.setPen(QColor(pal.apagado))
            p.setFont(_fonte(base, 14))
            p.drawText(self.rect(), Qt.AlignCenter, "Nenhuma tarefa nesta lista.")
        p.end()

    def _pintar_barra(self, p, t, i, cor, base):
        pal = tema.atual
        d_ini = d_fim = 0
        if self._arrasto is not None and self._arrasto[1].id == t.id:
            modo, _t, delta = self._arrasto
            if modo == "mover":
                d_ini = d_fim = delta
            elif modo == "ini":
                d_ini = delta
            else:
                d_fim = delta
        res = self._retangulo(t, i, d_ini, d_fim)
        if res is None:
            return
        r, x0, x1 = res
        if r.width() <= 0:
            return
        p.setPen(Qt.NoPen)
        p.setBrush(com_alfa(cor, 220 if self._arrasto is None or self._arrasto[1].id != t.id else 150))
        p.drawRoundedRect(QRectF(r), 6, 6)
        f = _fonte(base, 12, True)
        p.setFont(f)
        p.setPen(texto_sobre(cor))
        fm = QFontMetrics(f)
        if r.width() > 60:
            p.drawText(r.adjusted(8, 0, -6, 0), Qt.AlignVCenter | Qt.AlignLeft,
                       fm.elidedText(t.titulo, Qt.ElideRight, r.width() - 14))
        self.barras.append((r, t))

    # ---- mouse ----
    def _linha_em(self, y: int):
        i = y // LINHA_ALT
        return self.linhas[i] if 0 <= i < len(self.linhas) else None

    def _barra_em(self, pos):
        for r, t in reversed(self.barras):
            if r.contains(pos):
                return r, t
        return None

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        achado = self._barra_em(pos)
        t = achado[1] if achado else self._linha_em(pos.y())
        self._toque = t.id if (t is not None and e.button() == Qt.LeftButton) else None
        if t is not None:
            self.selecionada = t.id
            self.vista.janela.selecionar_tarefa(t.id)
        if e.button() == Qt.RightButton and t is not None:
            self.vista.janela.menu_da_tarefa_id(t.id, e.globalPosition().toPoint())
            return
        if e.button() == Qt.LeftButton and achado:
            r, t = achado
            borda = 7
            modo = "ini" if pos.x() <= r.left() + borda else "fim" if pos.x() >= r.right() - borda else "mover"
            self._pressionada = (modo, t, pos)
        else:
            self._pressionada = None
        self.update()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._pressionada is not None and e.buttons() & Qt.LeftButton:
            modo, t, inicio = self._pressionada
            delta = round((pos.x() - inicio.x()) / self._dw())
            if abs(pos.x() - inicio.x()) > 4:
                self._arrasto = (modo, t, delta)
                self.update()
            return
        achado = self._barra_em(pos)
        if achado:
            r, t = achado
            self.setCursor(Qt.SizeHorCursor if (pos.x() <= r.left() + 7 or pos.x() >= r.right() - 7)
                           else Qt.PointingHandCursor)
            a, b = self._periodo(t)
            QToolTip.showText(e.globalPosition().toPoint(), f"{t.titulo}\n{a:%d/%m} a {b:%d/%m}" if a != b
                              else f"{t.titulo}\n{a:%d/%m}", self)
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, e):
        arrasto, self._arrasto, self._pressionada = self._arrasto, None, None
        toque, self._toque = getattr(self, "_toque", None), None
        self.unsetCursor()
        if arrasto is not None:
            modo, t, delta = arrasto
            if delta:
                self.vista.aplicar(modo, t, delta)
        elif toque is not None and e.button() == Qt.LeftButton:
            self.vista.janela.abrir_cartao_da_tarefa(toque, QRect(self.mapToGlobal(e.position().toPoint()),
                                                                  QSize(1, 1)))
        self.update()

    def mouseDoubleClickEvent(self, e):
        pos = e.position().toPoint()
        t = self._linha_em(pos.y())
        if t is not None and t.prazo is None and pos.x() > ESQ:
            self.vista.definir_dia(t, self._dia_em_x(pos.x()))


class VistaLinhaTempo(QWidget):
    JANELAS = [("2 semanas", 14), ("4 semanas", 28), ("8 semanas", 56)]

    def __init__(self, janela):
        super().__init__()
        self.janela = janela
        self.n = 28
        self.ini = date.today() - timedelta(days=3)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        barra = QHBoxLayout()
        barra.setSpacing(6)
        self.btn_ante, self.btn_prox, self.btn_hoje = QPushButton("‹"), QPushButton("›"), QPushButton("Hoje")
        for b in (self.btn_ante, self.btn_prox):
            b.setFixedSize(34, 34)
            b.setCursor(Qt.PointingHandCursor)
        self.btn_hoje.setCursor(Qt.PointingHandCursor)
        barra.addWidget(self.btn_ante)
        barra.addWidget(self.btn_hoje)
        barra.addWidget(self.btn_prox)
        barra.addSpacing(10)
        self.combo = QComboBox()
        for nome, n in self.JANELAS:
            self.combo.addItem(nome, n)
        self.combo.setCurrentIndex(1)
        barra.addWidget(self.combo)
        barra.addStretch(1)
        dica = QLabel("Arraste a barra para mudar a data; arraste as pontas para esticar. "
                      "Duplo clique numa linha sem data define o dia.")
        dica.setObjectName("mensagemVazia")
        dica.setWordWrap(True)
        barra.addWidget(dica)
        lay.addLayout(barra)
        self.cabecalho = CabecalhoTempo()
        lay.addWidget(self.cabecalho)
        self.quadro = QuadroTempo(self)
        self.rolagem = QScrollArea()
        self.rolagem.setWidgetResizable(True)
        self.rolagem.setFrameShape(QScrollArea.NoFrame)
        self.rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.rolagem.setStyleSheet("QScrollArea { background: transparent; }")
        self.rolagem.setWidget(self.quadro)
        lay.addWidget(self.rolagem, 1)
        self.btn_ante.clicked.connect(lambda: self._mover(-self.n // 2))
        self.btn_prox.clicked.connect(lambda: self._mover(self.n // 2))
        self.btn_hoje.clicked.connect(self._hoje)
        self.combo.currentIndexChanged.connect(self._trocou)
        self._tarefas: list = []

    def _mover(self, dias: int):
        self.ini += timedelta(days=dias)
        self.carregar(self._tarefas)

    def _hoje(self):
        self.ini = date.today() - timedelta(days=3)
        self.carregar(self._tarefas)

    def _trocou(self, _):
        self.n = self.combo.currentData()
        self.carregar(self._tarefas)

    def carregar(self, tarefas: list):
        self._tarefas = tarefas
        com_data = sorted((t for t in tarefas if t.prazo), key=lambda t: (t.inicio or t.prazo, t.prazo, t.id))
        sem_data = [t for t in tarefas if not t.prazo]
        cores = {p.id: p.cor for p in self.janela.servico.banco.listar_projetos()}
        hoje = date.today()
        self.cabecalho.definir(self.ini, self.n, hoje)
        self.quadro.definir(com_data + sem_data, self.ini, self.n, hoje, cores)
        sel = self.janela.id_selecionado()
        self.quadro.selecionada = sel
        self.quadro.update()

    def aplicar(self, modo: str, t, delta: int):
        svc = self.janela.servico
        atual = svc.banco.obter_tarefa(t.id)
        inicio = atual.inicio or atual.prazo
        if modo == "mover":
            cal.mover_para(svc, t.id, inicio + timedelta(days=delta))
        elif modo == "fim":
            cal.definir_periodo(svc, t.id, inicio, max(atual.prazo + timedelta(days=delta), inicio))
        else:
            cal.definir_periodo(svc, t.id, min(inicio + timedelta(days=delta), atual.prazo), atual.prazo)
        self.janela.atualizar(manter_selecao=True)

    def definir_dia(self, t, dia: date):
        svc = self.janela.servico
        atual = svc.banco.obter_tarefa(t.id)
        atual.prazo = dia
        svc.salvar(atual)
        self.janela.atualizar(manter_selecao=True)


# ============================================================ Matriz de Eisenhower
class QuadranteMatriz(QFrame):
    def __init__(self, pagina: "PaginaMatriz", chave: str):
        super().__init__()
        self.pagina, self.chave = pagina, chave
        pal = tema.atual
        titulo, sub = matriz.NOMES[chave]
        cor = {"q1": pal.vermelho, "q2": "#f5a623", "q3": pal.destaque, "q4": pal.apagado}[chave]
        self.setObjectName("quadrante")
        self.setStyleSheet(f"QFrame#quadrante {{ background: {pal.barra}; border-radius: 10px; "
                           f"border-top: 3px solid {cor}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 8)
        lay.setSpacing(6)
        cab = QHBoxLayout()
        t = QLabel(titulo)
        t.setStyleSheet(f"font-weight: 600; font-size: 14px; color: {cor}; background: transparent;")
        self.sub = QLabel(sub)
        self.sub.setStyleSheet(f"color: {pal.apagado}; background: transparent; font-size: 12px;")
        self.contagem = QLabel("0")
        self.contagem.setStyleSheet(f"color: {pal.apagado}; background: transparent;")
        cab.addWidget(t)
        cab.addWidget(self.sub, 1)
        cab.addWidget(self.contagem)
        lay.addLayout(cab)
        self.lista = ListaCartoes(chave)
        lay.addWidget(self.lista, 1)
        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("+  Adicionar tarefa neste quadrante")
        self.entrada.setStyleSheet(f"QLineEdit {{ background: {pal.campo}; border: 1px solid transparent; "
                                   f"border-radius: 6px; padding: 8px 10px; }} QLineEdit:focus "
                                   f"{{ border: 1px solid {pal.destaque}; }}")
        lay.addWidget(self.entrada)
        self.lista.currentItemChanged.connect(lambda atual, _a: pagina.selecionou(self, atual))
        self.lista.soltou.connect(pagina.soltou)
        self.lista.alternou.connect(pagina.janela.alternar)
        self.lista.clicou_tarefa.connect(pagina.janela.abrir_cartao_da_tarefa)
        self.lista.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(self._menu)
        self.entrada.returnPressed.connect(lambda: pagina.nova(self.entrada, chave))

    def _menu(self, pos):
        item = self.lista.itemAt(pos)
        t = self.lista.tarefa_do_item(item)
        if t is not None:
            self.lista.setCurrentItem(item)
            self.pagina.janela.menu_da_tarefa_id(t.id, self.lista.mapToGlobal(pos))


class PaginaMatriz(QWidget):
    def __init__(self, janela):
        super().__init__()
        self.janela = janela
        self._selecionada: int | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 12)
        lay.setSpacing(10)
        cab = QHBoxLayout()
        titulo = QLabel("Matriz de Eisenhower")
        titulo.setObjectName("titulo")
        cab.addWidget(titulo)
        cab.addStretch(1)
        dica = QLabel("Importante = prioridade média ou alta · Urgente = prazo em até 2 dias. "
                      "Arraste para mudar prioridade e prazo.")
        dica.setObjectName("mensagemVazia")
        dica.setWordWrap(True)
        cab.addWidget(dica)
        lay.addLayout(cab)
        grade = QGridLayout()
        grade.setSpacing(12)
        self.quadrantes: dict[str, QuadranteMatriz] = {}
        for chave, (lin, col) in {matriz.Q1: (0, 0), matriz.Q2: (0, 1), matriz.Q3: (1, 0), matriz.Q4: (1, 1)}.items():
            q = QuadranteMatriz(self, chave)
            self.quadrantes[chave] = q
            grade.addWidget(q, lin, col)
        lay.addLayout(grade, 1)

    def atualizar(self):
        dados = self.janela.servico.matriz.quadrantes()
        for chave, q in self.quadrantes.items():
            q.lista.preencher(dados[chave])
            _preparar_lista(q.lista, self.janela)
            q.contagem.setText(str(len(dados[chave])))
            if self._selecionada is not None:
                q.lista.selecionar_id(self._selecionada)

    def selecionou(self, quadrante: QuadranteMatriz, item):
        t = quadrante.lista.tarefa_do_item(item)
        if t is None:
            return
        self._selecionada = t.id
        for q in self.quadrantes.values():
            if q is not quadrante:
                q.lista.selecionar_id(None)
        self.janela.selecionar_tarefa(t.id)

    def soltou(self, tarefa_id: int, chave):
        self.janela.servico.matriz.mover(tarefa_id, chave)
        self._selecionada = tarefa_id
        self.janela.atualizar(manter_selecao=True)

    def nova(self, campo: QLineEdit, chave: str):
        texto = campo.text().strip()
        if not texto:
            return
        svc = self.janela.servico
        t = svc.adicionar_rapido(texto)
        svc.matriz.mover(t.id, chave)
        campo.clear()
        self._selecionada = t.id
        self.janela.atualizar(selecionar_id=t.id)
