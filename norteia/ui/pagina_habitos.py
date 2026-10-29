"""Tela de Hábitos: marcar o dia, ver sequência e histórico do mês."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QMessageBox,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..core.habitos import SECOES
from . import icones, tema
from .dialogos import DialogoHabito
from .util import INICIAIS, MESES, com_alfa, texto_sobre


class BotaoMarca(QPushButton):
    """Círculo do hábito: vazio, parcial (arco) ou cheio com check."""

    def __init__(self, cor: str, meta: int):
        super().__init__()
        self.cor, self.meta, self.qtd = cor, meta, 0
        self.setFixedSize(40, 40)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.setStyleSheet("QPushButton { border: none; background: transparent; }")

    def definir(self, qtd: int):
        self.qtd = qtd
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(5, 5, 30, 30)
        feito = self.qtd >= self.meta
        p.setPen(QPen(QColor(self.cor), 2))
        p.setBrush(QColor(self.cor) if feito else Qt.NoBrush)
        p.drawEllipse(r)
        if feito:
            p.setPen(QPen(texto_sobre(self.cor), 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawLine(QPointF(13, 20.5), QPointF(18, 25.5))
            p.drawLine(QPointF(18, 25.5), QPointF(27.5, 14.5))
        elif self.qtd > 0 and self.meta > 1:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(self.cor), 5))
            p.drawArc(r.adjusted(2.5, 2.5, -2.5, -2.5), 90 * 16, int(-self.qtd / self.meta * 360 * 16))
        if self.meta > 1:
            f = QFont(self.font())
            f.setPixelSize(11)
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
            p.setPen(QColor(texto_sobre(self.cor) if feito else tema.atual.texto))
            p.drawText(r, Qt.AlignCenter, str(self.qtd) if not feito else "")
        p.end()


CELULA = 30                    # largura de cada dia na faixa semanal


class FaixaSemana(QWidget):
    """Sete círculos (a semana atual) de um hábito. Clicar num dia de hoje ou do passado marca ou desmarca."""
    clicou = Signal(object)

    def __init__(self, habito, dias: list[date], marc: dict, hoje: date):
        super().__init__()
        self.h, self.dias, self.marc, self.hoje = habito, dias, marc, hoje
        self.setFixedSize(CELULA * 7, 36)
        self.setCursor(Qt.PointingHandCursor)

    def _dia_em(self, x: float) -> date | None:
        i = int(x // CELULA)
        return self.dias[i] if 0 <= i < 7 else None

    def paintEvent(self, _):
        pal = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.h
        for i, d in enumerate(self.dias):
            q = self.marc.get(d, 0)
            c = QPointF(i * CELULA + CELULA / 2, self.height() / 2)
            raio = 10
            if q >= h.meta and q > 0:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(h.cor))
                p.drawEllipse(c, raio, raio)
                p.setPen(QPen(texto_sobre(h.cor), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawLine(QPointF(c.x() - 4, c.y() + 0.5), QPointF(c.x() - 1, c.y() + 3.5))
                p.drawLine(QPointF(c.x() - 1, c.y() + 3.5), QPointF(c.x() + 4.5, c.y() - 3))
            elif not h.agendado(d):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(tema.atual.barra_rolagem))
                p.drawEllipse(c, 2, 2)
            else:
                cor = QColor(h.cor) if d == self.hoje else QColor(tema.atual.sutil)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(cor, 1.6))
                p.drawEllipse(c, raio, raio)
                if q > 0 and h.meta > 1:
                    p.setPen(QPen(QColor(h.cor), 3))
                    p.drawArc(QRectF(c.x() - 7, c.y() - 7, 14, 14), 90 * 16, int(-q / h.meta * 360 * 16))
        p.end()

    def mousePressEvent(self, e):
        d = self._dia_em(e.position().x())
        if e.button() == Qt.LeftButton and d is not None and d <= self.hoje:
            self.clicou.emit(d)
            e.accept()
        else:
            super().mousePressEvent(e)


class CabecalhoSemana(QWidget):
    """Letra e número dos sete dias, alinhado com a faixa de cada hábito."""

    def __init__(self, dias: list[date], hoje: date):
        super().__init__()
        self.dias, self.hoje = dias, hoje
        self.setFixedSize(CELULA * 7, 40)

    def paintEvent(self, _):
        pal = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont(self.font())
        for i, d in enumerate(self.dias):
            cx = i * CELULA + CELULA / 2
            f.setPixelSize(10)
            p.setFont(f)
            p.setPen(QColor(pal.apagado))
            p.drawText(QRectF(i * CELULA, 0, CELULA, 14), Qt.AlignCenter, INICIAIS[d.weekday()])
            f.setPixelSize(12)
            p.setFont(f)
            if d == self.hoje:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(pal.destaque))
                p.drawEllipse(QPointF(cx, 27), 10, 10)
                p.setPen(QColor("#ffffff"))
            else:
                p.setPen(QColor(pal.texto))
            p.drawText(QRectF(i * CELULA, 17, CELULA, 20), Qt.AlignCenter, str(d.day))
        p.end()


class LinhaHabito(QFrame):
    clicou = Signal(str)          # uuid: selecionar
    marcou = Signal(str)          # uuid: marcar hoje
    marcou_dia = Signal(str, object)

    def __init__(self, habito, qtd: int, atual: int, melhor: int, selecionado: bool,
                 dias: list[date] | None = None, marc: dict | None = None, hoje: date | None = None):
        super().__init__()
        pal = tema.atual
        self.uuid = habito.uuid
        self.setObjectName("linhaHabito")
        fundo = pal.linha_selecionada if selecionado else "transparent"
        self.setStyleSheet(f"QFrame#linhaHabito {{ background: {fundo}; border-radius: 8px; }}"
                           f"QFrame#linhaHabito:hover {{ background: "
                           f"{pal.linha_selecionada if selecionado else pal.linha_hover}; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 14, 4)
        self.botao = BotaoMarca(habito.cor, habito.meta)
        self.botao.definir(qtd)
        self.botao.clicked.connect(lambda: self.marcou.emit(self.uuid))
        lay.addWidget(self.botao)
        col = QVBoxLayout()
        col.setSpacing(0)
        nome = QLabel(habito.nome)
        nome.setStyleSheet("font-size: 14px; background: transparent;" +
                           (f"color: {pal.apagado};" if habito.arquivado else ""))
        meta = (f"{qtd}/{habito.meta} {habito.unidade}" if habito.meta > 1 else "")
        sub = QLabel(meta)
        sub.setStyleSheet(f"font-size: 11px; color: {pal.apagado}; background: transparent;")
        col.addWidget(nome)
        if meta:
            col.addWidget(sub)
        lay.addLayout(col, 1)
        seq = QLabel(f"{atual} dia{'s' if atual != 1 else ''}")
        seq.setFixedWidth(54)
        seq.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        seq.setToolTip(f"Sequência atual: {atual}. Melhor: {melhor}.")
        seq.setStyleSheet(f"color: {pal.apagado}; background: transparent; font-size: 11px;")
        lay.addWidget(seq)
        self.faixa = None
        if dias:
            self.faixa = FaixaSemana(habito, dias, marc or {}, hoje or date.today())
            self.faixa.clicou.connect(lambda d: self.marcou_dia.emit(self.uuid, d))
            lay.addWidget(self.faixa)

    def mousePressEvent(self, e):
        self.clicou.emit(self.uuid)
        super().mousePressEvent(e)


class CartaoHabito(QFrame):
    """Cartão da visão em grade."""
    clicou = Signal(str)
    marcou = Signal(str)

    def __init__(self, habito, qtd: int, atual: int, selecionado: bool):
        super().__init__()
        pal = tema.atual
        self.uuid = habito.uuid
        self.setObjectName("cartaoHabito")
        self.setMinimumHeight(104)
        borda = pal.destaque if selecionado else "transparent"
        self.setStyleSheet(f"QFrame#cartaoHabito {{ background: {pal.barra}; border-radius: 10px; "
                           f"border: 1px solid {borda}; }} QFrame#cartaoHabito:hover {{ background: {pal.barra_hover}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        topo = QHBoxLayout()
        nome = QLabel(habito.nome)
        nome.setWordWrap(True)
        nome.setStyleSheet("font-size: 13px; font-weight: 600; background: transparent; border: none;")
        topo.addWidget(nome, 1)
        self.botao = BotaoMarca(habito.cor, habito.meta)
        self.botao.definir(qtd)
        self.botao.clicked.connect(lambda: self.marcou.emit(self.uuid))
        topo.addWidget(self.botao, 0, Qt.AlignTop)
        lay.addLayout(topo)
        lay.addStretch(1)
        meta = f"{qtd}/{habito.meta} {habito.unidade}  ·  " if habito.meta > 1 else ""
        rod = QLabel(f"{meta}{atual} dia{'s' if atual != 1 else ''} seguidos")
        rod.setStyleSheet(f"font-size: 11px; color: {pal.apagado}; background: transparent; border: none;")
        lay.addWidget(rod)

    def mousePressEvent(self, e):
        self.clicou.emit(self.uuid)
        super().mousePressEvent(e)


class MesHabito(QWidget):
    """Grade do mês. Clicar num dia (passado ou hoje) marca ou desmarca."""
    clicou = Signal(object)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(250)
        self.setMouseTracking(True)
        self.cor = tema.atual.destaque
        self.ano, self.mes = date.today().year, date.today().month
        self.estados: list[tuple[date, str]] = []
        self.segunda = False
        self._celulas: list[tuple[QRectF, date, str]] = []

    def definir(self, ano, mes, estados, cor, segunda=False):
        self.ano, self.mes, self.estados, self.cor, self.segunda = ano, mes, estados, cor, segunda
        self.update()

    def paintEvent(self, _):
        pal = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        base = self.font()
        larg = self.width() / 7
        topo = 24
        alt = min(44.0, (self.height() - topo) / 6)
        nomes = INICIAIS if self.segunda else INICIAIS[6:] + INICIAIS[:6]
        f = QFont(base)
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(QColor(pal.apagado))
        for i, n in enumerate(nomes):
            p.drawText(QRectF(i * larg, 0, larg, topo), Qt.AlignCenter, n)
        self._celulas = []
        if not self.estados:
            p.end()
            return
        primeiro = self.estados[0][0]
        deslocamento = primeiro.weekday() if self.segunda else (primeiro.weekday() + 1) % 7
        f.setPixelSize(12)
        p.setFont(f)
        for i, (dia, estado) in enumerate(self.estados):
            pos = i + deslocamento
            linha, col = divmod(pos, 7)
            r = QRectF(col * larg, topo + linha * alt, larg, alt).adjusted(4, 3, -4, -3)
            lado = min(r.width(), r.height())
            c = QRectF(r.center().x() - lado / 2, r.center().y() - lado / 2, lado, lado)
            self._celulas.append((r, dia, estado))
            if estado == "feito":
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(self.cor))
                p.drawEllipse(c)
                p.setPen(texto_sobre(self.cor))
            elif estado == "parcial":
                p.setPen(Qt.NoPen)
                p.setBrush(com_alfa(self.cor, 90))
                p.drawEllipse(c)
                p.setPen(QColor(pal.texto))
            elif estado == "perdido":
                p.setPen(QPen(com_alfa(pal.vermelho, 150), 1.4))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(c)
                p.setPen(QColor(pal.apagado))
            elif estado == "pendente":
                p.setPen(QPen(QColor(self.cor), 1.6))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(c)
                p.setPen(QColor(pal.texto))
            else:
                p.setPen(QColor(pal.sutil if estado == "livre" else pal.apagado))
            p.drawText(c, Qt.AlignCenter, str(dia.day))
        p.end()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        for r, dia, estado in self._celulas:
            if r.contains(e.position()) and estado not in ("futuro",):
                self.clicou.emit(dia)
                return


class PaginaHabitos(QWidget):
    def __init__(self, janela):
        super().__init__()
        self.janela = janela
        self.selecionado: str | None = None
        self.modo_grade = False
        self.recolhidas: set[str] = set()
        self.ano, self.mes = date.today().year, date.today().month
        pal = tema.atual
        lay = QHBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 12)
        lay.setSpacing(24)

        # ---- lista ----
        esq = QVBoxLayout()
        cab = QHBoxLayout()
        cab.setSpacing(2)
        titulo = QLabel("Hábito")
        titulo.setObjectName("titulo")
        cab.addWidget(titulo)
        self.btn_filtro = self._icone_plano("seta-baixo", "Filtrar hábitos", 14)
        self.menu_filtro = QMenu(self)
        self.chk_arquivados = QCheckBox("Mostrar arquivados", self)       # estado do filtro (fica no menu)
        self.chk_arquivados.hide()
        self.acao_arquivados = QAction("Mostrar arquivados", self, checkable=True)
        self.acao_arquivados.toggled.connect(self.chk_arquivados.setChecked)
        self.chk_arquivados.toggled.connect(self.acao_arquivados.setChecked)
        self.menu_filtro.addAction(self.acao_arquivados)
        self.btn_filtro.setMenu(self.menu_filtro)
        cab.addWidget(self.btn_filtro)
        cab.addStretch(1)
        self.btn_visao = self._icone_plano("kanban", "Alternar entre lista e grade")
        cab.addWidget(self.btn_visao)
        self.btn_novo = self._icone_plano("mais", "Novo hábito")
        cab.addWidget(self.btn_novo)
        self.btn_menu = self._icone_plano("reticencias", "Mais")
        self.menu_mais = QMenu(self)
        self.menu_mais.addAction("Recolher todas as seções", lambda: self._recolher_todas(True))
        self.menu_mais.addAction("Expandir todas as seções", lambda: self._recolher_todas(False))
        self.btn_menu.setMenu(self.menu_mais)
        cab.addWidget(self.btn_menu)
        esq.addLayout(cab)
        self.rot_hoje = QLabel("")
        self.rot_hoje.setObjectName("mensagemVazia")
        esq.addWidget(self.rot_hoje)
        self.quadro_semana = QHBoxLayout()           # cabeçalho dos dias da semana (só na visão em lista)
        esq.addLayout(self.quadro_semana)
        self.rolagem = QScrollArea()
        self.rolagem.setWidgetResizable(True)
        self.rolagem.setFrameShape(QScrollArea.NoFrame)
        self.rolagem.setStyleSheet("QScrollArea { background: transparent; }")
        self.miolo = QWidget()
        self.miolo.setStyleSheet("background: transparent;")
        self.caixa = QVBoxLayout(self.miolo)
        self.caixa.setContentsMargins(0, 0, 0, 0)
        self.caixa.setSpacing(2)
        self.rolagem.setWidget(self.miolo)
        esq.addWidget(self.rolagem, 1)
        lado_esq = QWidget()
        lado_esq.setLayout(esq)
        lado_esq.setMinimumWidth(520)
        lay.addWidget(lado_esq, 5)

        # ---- detalhe ----
        self.detalhe = QFrame()
        self.detalhe.setObjectName("quadroHabito")
        self.detalhe.setStyleSheet(f"QFrame#quadroHabito {{ background: {pal.barra}; border-radius: 10px; }}")
        det = QVBoxLayout(self.detalhe)
        det.setContentsMargins(20, 18, 20, 18)
        det.setSpacing(10)
        self.det_titulo = QLabel("")
        self.det_titulo.setStyleSheet("font-size: 18px; font-weight: 600; background: transparent;")
        det.addWidget(self.det_titulo)
        self.det_sub = QLabel("")
        self.det_sub.setStyleSheet(f"color: {pal.apagado}; background: transparent;")
        det.addWidget(self.det_sub)
        cartoes = QHBoxLayout()
        self.n_atual, self.n_melhor, self.n_total, self.n_taxa = (self._cartao(cartoes, t) for t in
                                                                  ("Sequência", "Melhor", "Total", "Últimos 30 dias"))
        det.addLayout(cartoes)
        nav = QHBoxLayout()
        self.btn_ante, self.btn_prox = QPushButton("‹"), QPushButton("›")
        for b in (self.btn_ante, self.btn_prox):
            b.setFixedSize(30, 30)
            b.setStyleSheet("QPushButton { padding: 0; font-size: 16px; }")
            b.setCursor(Qt.PointingHandCursor)
        self.mes_titulo = QLabel("")
        self.mes_titulo.setStyleSheet("font-weight: 600; background: transparent;")
        nav.addWidget(self.mes_titulo, 1)
        nav.addWidget(self.btn_ante)
        nav.addWidget(self.btn_prox)
        det.addLayout(nav)
        self.grade = MesHabito()
        det.addWidget(self.grade, 1)
        acoes = QHBoxLayout()
        self.btn_editar = QPushButton("Editar")
        self.btn_arquivar = QPushButton("Arquivar")
        self.btn_apagar = QPushButton("Apagar")
        self.btn_apagar.setObjectName("perigo")
        for b in (self.btn_editar, self.btn_arquivar, self.btn_apagar):
            b.setCursor(Qt.PointingHandCursor)
            acoes.addWidget(b)
        acoes.addStretch(1)
        det.addLayout(acoes)
        self.vazio = QLabel("Crie um hábito para começar.\nEx.: beber água, estudar 1 hora, treinar.")
        self.vazio.setAlignment(Qt.AlignCenter)
        self.vazio.setObjectName("mensagemVazia")
        lay.addWidget(self.detalhe, 4)
        lay.addWidget(self.vazio, 4)

        self.btn_novo.clicked.connect(self.novo)
        self.btn_editar.clicked.connect(self.editar)
        self.btn_arquivar.clicked.connect(self.arquivar)
        self.btn_apagar.clicked.connect(lambda: self.apagar())
        self.btn_ante.clicked.connect(lambda: self._navegar(-1))
        self.btn_prox.clicked.connect(lambda: self._navegar(+1))
        self.grade.clicou.connect(self._clicou_dia)
        self.chk_arquivados.toggled.connect(lambda _: self.atualizar())
        self.btn_visao.clicked.connect(self.alternar_visao)
        self.atualizar()

    @staticmethod
    def _icone_plano(nome: str, dica: str, lado: int = 18) -> QPushButton:
        b = QPushButton()
        b.setObjectName("btnIcone")
        b.setIcon(icones.icone(nome, tema.atual.texto, lado))
        b.setIconSize(QSize(lado, lado))
        b.setFixedSize(30 if lado >= 18 else 24, 30)
        b.setToolTip(dica)
        b.setCursor(Qt.PointingHandCursor)
        return b

    @staticmethod
    def _cartao(caixa: QHBoxLayout, titulo: str) -> QLabel:
        pal = tema.atual
        q = QFrame()
        q.setStyleSheet(f"QFrame {{ background: {pal.campo}; border-radius: 8px; }}")
        l = QVBoxLayout(q)
        l.setContentsMargins(12, 8, 12, 8)
        l.setSpacing(0)
        num = QLabel("0")
        num.setStyleSheet("font-size: 20px; font-weight: 600; background: transparent;")
        rot = QLabel(titulo)
        rot.setStyleSheet(f"font-size: 11px; color: {pal.apagado}; background: transparent;")
        l.addWidget(num)
        l.addWidget(rot)
        caixa.addWidget(q)
        return num

    # ---- dados ----
    @property
    def habitos(self):
        return self.janela.servico.habitos

    def _segunda(self) -> bool:
        return bool(self.janela.prefs.get("semana_comeca_segunda", False))

    def _lista(self):
        hs = self.habitos.listar(arquivados=False)
        if self.chk_arquivados.isChecked():
            hs += self.habitos.listar(arquivados=True)
        return hs

    def _dias_da_semana(self, hoje: date) -> list[date]:
        ini = hoje - timedelta(days=hoje.weekday() if self._segunda() else (hoje.weekday() + 1) % 7)
        return [ini + timedelta(days=i) for i in range(7)]

    def alternar_visao(self):
        self.modo_grade = not self.modo_grade
        self.btn_visao.setIcon(icones.icone("lista" if self.modo_grade else "kanban", tema.atual.texto, 18))
        self.atualizar()

    def _recolher_todas(self, sim: bool):
        self.recolhidas = set(SECOES) if sim else set()
        self.atualizar()

    def _alternar_secao(self, nome: str):
        self.recolhidas ^= {nome}
        self.atualizar()

    def _cabecalho_secao(self, nome: str, quantos: int, recolhida: bool) -> QPushButton:
        pal = tema.atual
        b = QPushButton(f"  {nome}   {quantos}")
        b.setIcon(icones.icone("seta-dir" if recolhida else "seta-baixo", pal.apagado, 12))
        b.setIconSize(QSize(12, 12))
        b.setCursor(Qt.PointingHandCursor)
        b.setStyleSheet(f"QPushButton {{ background: transparent; border: none; text-align: left; "
                        f"color: {pal.apagado}; font-size: 12px; font-weight: 600; padding: 10px 6px 4px 6px; }}"
                        f"QPushButton:hover {{ color: {pal.texto}; border: none; }}")
        b.clicked.connect(lambda: self._alternar_secao(nome))
        return b

    def atualizar(self):
        hoje = date.today()
        lista = self._lista()
        while self.caixa.count():
            w = self.caixa.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        while self.quadro_semana.count():
            w = self.quadro_semana.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        if self.selecionado not in {h.uuid for h in lista}:
            self.selecionado = lista[0].uuid if lista else None
        todas = self.habitos.todas_as_marcacoes()
        dias = self._dias_da_semana(hoje)
        feitos = 0
        previstos = 0
        por_secao: dict[str, list] = {n: [] for n in SECOES}
        for h in lista:
            marc = todas.get(h.uuid, {})
            qtd = marc.get(hoje, 0)
            atual, melhor = self.habitos.sequencia(h, hoje, marc)
            if not h.arquivado and h.agendado(hoje):
                previstos += 1
                feitos += qtd >= h.meta
            por_secao[h.secao if h.secao in por_secao else "Outros"].append((h, marc, qtd, atual, melhor))
        if lista and not self.modo_grade:
            self.quadro_semana.addStretch(1)
            self.quadro_semana.addWidget(CabecalhoSemana(dias, hoje))
            self.quadro_semana.addSpacing(14)
            self.quadro_semana.setContentsMargins(0, 4, 0, 0)
        for nome in SECOES:
            itens = por_secao[nome]
            if not itens:
                continue
            recolhida = nome in self.recolhidas
            self.caixa.addWidget(self._cabecalho_secao(nome, len(itens), recolhida))
            if recolhida:
                continue
            if self.modo_grade:
                grade = QWidget()
                g = QGridLayout(grade)
                g.setContentsMargins(0, 0, 0, 0)
                g.setSpacing(10)
                for i, (h, marc, qtd, atual, melhor) in enumerate(itens):
                    c = CartaoHabito(h, qtd, atual, h.uuid == self.selecionado)
                    c.clicou.connect(self.selecionar)
                    c.marcou.connect(self.marcar_hoje)
                    g.addWidget(c, i // 3, i % 3)
                for col in range(3):
                    g.setColumnStretch(col, 1)
                self.caixa.addWidget(grade)
                continue
            for h, marc, qtd, atual, melhor in itens:
                linha = LinhaHabito(h, qtd, atual, melhor, h.uuid == self.selecionado, dias, marc, hoje)
                linha.clicou.connect(self.selecionar)
                linha.marcou.connect(self.marcar_hoje)
                linha.marcou_dia.connect(self.marcar_dia)
                self.caixa.addWidget(linha)
        self.caixa.addStretch(1)
        self.rot_hoje.setText(f"Hoje: {feitos} de {previstos} feitos" if previstos else "Nada marcado para hoje.")
        self.detalhe.setVisible(self.selecionado is not None)
        self.vazio.setVisible(self.selecionado is None)
        self._detalhar()

    def marcar_dia(self, uuid: str, dia: date):
        h = self.habitos.obter(uuid)
        if h is None or dia > date.today():
            return
        if dia < h.inicio:
            h.inicio = dia
            self.habitos.salvar(h)
        self.habitos.alternar(h, dia)
        self.selecionado = uuid
        self.atualizar()

    def _detalhar(self):
        h = self.habitos.obter(self.selecionado) if self.selecionado else None
        if h is None:
            return
        hoje = date.today()
        marc = self.habitos.marcacoes(h)
        atual, melhor = self.habitos.sequencia(h, hoje, marc)
        self.det_titulo.setText(h.nome)
        dias = ", ".join(n for i, n in enumerate(["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]) if i in h.dias)
        meta = f"{h.meta} {h.unidade} por dia" if h.meta > 1 else "uma vez por dia"
        lembrete = f" · lembrete às {h.lembrete}" if h.lembrete else ""
        prazo = f" · {h.dias_meta} dias de meta" if h.dias_meta else ""
        self.det_sub.setText(f"{meta} · {dias if len(h.dias) < 7 else 'todos os dias'}{lembrete}{prazo}")
        self.n_atual.setText(str(atual))
        self.n_melhor.setText(str(melhor))
        self.n_total.setText(str(self.habitos.total_feitos(h, marc)))
        self.n_taxa.setText(f"{round(self.habitos.taxa(h, hoje - timedelta(days=29), hoje, marc) * 100)}%")
        self.mes_titulo.setText(f"{MESES[self.mes - 1].capitalize()} de {self.ano}")
        self.grade.definir(self.ano, self.mes, self.habitos.mes(h, self.ano, self.mes, hoje), h.cor, self._segunda())
        self.btn_arquivar.setText("Desarquivar" if h.arquivado else "Arquivar")

    # ---- ações ----
    def selecionar(self, uuid: str):
        self.selecionado = uuid
        self.atualizar()

    def marcar_hoje(self, uuid: str):
        h = self.habitos.obter(uuid)
        if h is None:
            return
        if h.meta > 1:
            self.habitos.incrementar(h, date.today())
        else:
            self.habitos.alternar(h, date.today())
        self.selecionado = uuid
        self.atualizar()

    def _clicou_dia(self, dia: date):
        h = self.habitos.obter(self.selecionado) if self.selecionado else None
        if h is not None and dia <= date.today():
            if dia < h.inicio:                     # marcar um dia antigo faz o hábito "começar" naquele dia
                h.inicio = dia
                self.habitos.salvar(h)
            self.habitos.alternar(h, dia)
            self.atualizar()

    def _navegar(self, passo: int):
        m = self.mes - 1 + passo
        self.ano, self.mes = self.ano + m // 12, m % 12 + 1
        self._detalhar()

    def novo(self, dados: dict | None = None):
        if not isinstance(dados, dict):
            dlg = DialogoHabito(self)
            if dlg.exec() != DialogoHabito.Accepted:
                return
            dados = dlg.resultado()
        h = self.habitos.criar(**dados)
        self.selecionado = h.uuid
        self.atualizar()

    def editar(self, dados: dict | None = None):
        h = self.habitos.obter(self.selecionado) if self.selecionado else None
        if h is None:
            return
        if not isinstance(dados, dict):
            dlg = DialogoHabito(self, h)
            if dlg.exec() != DialogoHabito.Accepted:
                return
            dados = dlg.resultado()
        h.nome, h.cor, h.meta, h.unidade = dados["nome"], dados["cor"], dados["meta"], dados["unidade"]
        h.dias, h.lembrete = dados["dias"], dados["lembrete"]
        h.secao = dados.get("secao", h.secao)
        h.dias_meta = dados.get("dias_meta", h.dias_meta)
        if dados.get("inicio") is not None:
            h.inicio = dados["inicio"]
        self.habitos.salvar(h)
        self.atualizar()

    def arquivar(self):
        h = self.habitos.obter(self.selecionado) if self.selecionado else None
        if h is not None:
            self.habitos.arquivar(h.uuid, not h.arquivado)
            self.atualizar()

    def apagar(self, confirmar: bool = True):
        h = self.habitos.obter(self.selecionado) if self.selecionado else None
        if h is None:
            return
        if confirmar and QMessageBox.question(
                self, "Apagar hábito", f"Apagar “{h.nome}” e todo o histórico dele?") != QMessageBox.Yes:
            return
        self.habitos.apagar(h.uuid)
        self.selecionado = None
        self.atualizar()
