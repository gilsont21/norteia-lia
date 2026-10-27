"""Tela de Foco: Pomodoro e cronômetro, ligados a uma tarefa."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, QPointF, QRectF, QSize, Qt, QTime, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QPushButton, QScrollArea,
                               QSpinBox, QTimeEdit, QVBoxLayout, QWidget)

from ..core import TODAS
from ..core.foco import ConfigFoco, Cronometro, Sessao, formatar_duracao
from . import icones, tema
from .popovers import Flutuante

NOMES_FASE = {Cronometro.FOCO: "Foco", Cronometro.PAUSA_CURTA: "Pausa curta",
              Cronometro.PAUSA_LONGA: "Pausa longa", Cronometro.PARADO: "Pronto para começar"}


def texto_relogio(segundos: float) -> str:
    s = int(round(segundos))
    h, resto = divmod(s, 3600)
    m, s = divmod(resto, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class AnelFoco(QWidget):
    """Anel fino com o tempo no meio. No Pomodoro o arco se esvazia; no cronômetro vira um círculo de tracinhos."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(260, 260)
        self.fracao = 1.0           # 1 = cheio
        self.texto = "25:00"
        self.sub = ""
        self.cor = tema.atual.destaque
        self.tracos = False

    def definir(self, fracao: float, texto: str, sub: str, cor: str, tracos: bool = False):
        self.fracao, self.texto, self.sub, self.cor, self.tracos = (
            max(0.0, min(1.0, fracao)), texto, sub, cor, tracos)
        self.update()

    def paintEvent(self, _):
        pal = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        lado = min(self.width(), self.height(), 300) - 16
        r = QRectF((self.width() - lado) / 2, (self.height() - lado) / 2, lado, lado)
        p.setBrush(Qt.NoBrush)
        if self.tracos:
            centro = r.center()
            n = 60
            marcados = int(self.fracao * n)
            for i in range(n):
                ang = math.radians(i * 360 / n - 90)
                r0, r1 = lado / 2 - 9, lado / 2 - 2
                cor = QColor(self.cor) if i < marcados else QColor("#2c2c2c")
                p.setPen(QPen(cor, 2, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(centro.x() + r0 * math.cos(ang), centro.y() + r0 * math.sin(ang)),
                           QPointF(centro.x() + r1 * math.cos(ang), centro.y() + r1 * math.sin(ang)))
        else:
            p.setPen(QPen(QColor("#2e2e2e"), 3))
            p.drawEllipse(r)
            if self.fracao > 0:
                p.setPen(QPen(QColor(self.cor), 4, Qt.SolidLine, Qt.RoundCap))
                p.drawArc(r, 90 * 16, int(-self.fracao * 360 * 16))
        f = QFont(self.font())
        f.setPixelSize(int(lado * 0.19))
        f.setWeight(QFont.Normal)
        p.setFont(f)
        p.setPen(QColor(pal.texto))
        p.drawText(r, Qt.AlignCenter, self.texto)
        f.setPixelSize(max(int(lado * 0.05), 10))
        p.setFont(f)
        p.setPen(QColor(pal.apagado))
        p.drawText(r.adjusted(0, lado * 0.26, 0, 0), Qt.AlignHCenter | Qt.AlignVCenter, self.sub)
        p.end()


def _hm(d: datetime) -> str:
    return f"{d.hour}:{d.minute:02d}"


def _duracao_curta(segundos: int) -> str:
    m = int(segundos) // 60
    return f"{m // 60}h{m % 60:02d}m" if m >= 60 else f"{m}m"


def _valor_com_unidades(segundos: int) -> str:
    m = int(segundos) // 60
    pq = "font-size: 10px; color: #8c8c8c;"
    if m >= 60:
        return f"{m // 60}<span style='{pq}'> h </span>{m % 60}<span style='{pq}'> m</span>"
    return f"{m}<span style='{pq}'> m</span>"


def _nome_data(d: date) -> str:
    meses = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    return f"{d.day} de {meses[d.month - 1]} de {d.year}"


class SeletorFoco(Flutuante):
    """Escolhe em que focar: uma tarefa ou um hábito (com busca)."""

    def __init__(self, pagina, parent=None):
        super().__init__(parent)
        self.pagina = pagina
        self.setFixedWidth(260)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        abas = QHBoxLayout()
        self.aba_tarefa, self.aba_habito = QPushButton("Tarefa"), QPushButton("Hábito")
        for b in (self.aba_tarefa, self.aba_habito):
            b.setObjectName("aba")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            abas.addWidget(b)
        abas.addStretch(1)
        lay.addLayout(abas)
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar")
        lay.addWidget(self.busca)
        self.lista = QListWidget()
        self.lista.setFixedHeight(230)
        lay.addWidget(self.lista)
        self.aba = "tarefa"
        self.aba_tarefa.clicked.connect(lambda: self.definir_aba("tarefa"))
        self.aba_habito.clicked.connect(lambda: self.definir_aba("habito"))
        self.busca.textChanged.connect(lambda _: self._montar())
        self.lista.itemClicked.connect(self._clicou)
        self.definir_aba("tarefa")

    def definir_aba(self, aba: str):
        self.aba = aba
        self.aba_tarefa.setChecked(aba == "tarefa")
        self.aba_habito.setChecked(aba == "habito")
        self._montar()

    def _montar(self):
        pal = tema.atual
        self.lista.clear()
        q = self.busca.text().strip().lower()
        svc = self.pagina.servico
        livre = QListWidgetItem("Sem tarefa (foco livre)")
        livre.setData(Qt.UserRole, ("livre", None, "Foco"))
        self.lista.addItem(livre)
        if self.aba == "habito":
            for h in svc.habitos.listar():
                if q and q not in h.nome.lower():
                    continue
                it = QListWidgetItem(h.nome)
                it.setData(Qt.UserRole, ("habito", h.uuid, h.nome))
                self.lista.addItem(it)
            return
        hoje = date.today()
        grupos: dict[str, list] = {"Em atraso": [], "Hoje": [], "Próximas": [], "Sem data": []}
        for t in svc.listar(TODAS):
            if t.finalizada or t.eh_nota or (q and q not in t.titulo.lower()):
                continue
            if t.prazo is None:
                grupos["Sem data"].append(t)
            elif t.prazo < hoje:
                grupos["Em atraso"].append(t)
            elif t.prazo == hoje:
                grupos["Hoje"].append(t)
            else:
                grupos["Próximas"].append(t)
        for nome, itens in grupos.items():
            if not itens:
                continue
            cab = QListWidgetItem(nome)
            cab.setFlags(Qt.NoItemFlags)
            cab.setForeground(QColor(pal.apagado))
            self.lista.addItem(cab)
            for t in itens[:60]:
                it = QListWidgetItem(t.titulo)
                it.setData(Qt.UserRole, ("tarefa", t.id, t.titulo))
                if nome == "Em atraso":
                    it.setToolTip(f"{t.prazo:%d/%m/%Y}")
                self.lista.addItem(it)

    def _clicou(self, item: QListWidgetItem):
        dado = item.data(Qt.UserRole)
        if dado:
            self.pagina.definir_alvo(*dado)
            self.close()


class DialogoRegistroFoco(QDialog):
    """Adiciona à mão um foco que você fez sem o cronômetro."""

    def __init__(self, parent, tarefas: list[tuple[str, int | None]]):
        super().__init__(parent)
        self.setWindowTitle("Adicionar foco")
        lay = QFormLayout(self)
        self.data = QDateEdit()
        self.data.setCalendarPopup(True)
        self.data.setDisplayFormat("dd/MM/yyyy")
        self.data.setDate(QDate.currentDate())
        self.hora = QTimeEdit()
        self.hora.setDisplayFormat("HH:mm")
        self.hora.setTime(QTime.currentTime())
        self.minutos = QSpinBox()
        self.minutos.setRange(1, 600)
        self.minutos.setValue(25)
        self.minutos.setSuffix(" min")
        self.tarefa = QComboBox()
        for nome, valor in tarefas:
            self.tarefa.addItem(nome, valor)
        lay.addRow("Dia", self.data)
        lay.addRow("Início", self.hora)
        lay.addRow("Duração", self.minutos)
        lay.addRow("Tarefa", self.tarefa)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addRow(bb)

    def sessao(self) -> Sessao:
        d, h = self.data.date(), self.hora.time()
        return Sessao(datetime(d.year(), d.month(), d.day(), h.hour(), h.minute()), self.minutos.value() * 60,
                      "pomodoro", True, self.tarefa.currentData())


class LinhaRegistro(QFrame):
    def __init__(self, pagina, s: Sessao):
        super().__init__()
        self.pagina, self.s = pagina, s
        pal = tema.atual
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 5, 4, 5)
        lay.setSpacing(8)
        ico = QLabel()
        ico.setPixmap(icones.pixmap("foco", pal.destaque if s.completa else pal.apagado, 14))
        fim = s.inicio + timedelta(seconds=s.duracao_s)
        hora = QLabel(f"{_hm(s.inicio)} - {_hm(fim)}")
        hora.setStyleSheet(f"font-size: 11px; color: {pal.texto if s.completa else pal.apagado};")
        dur = QLabel(_duracao_curta(s.duracao_s))
        dur.setStyleSheet(f"font-size: 11px; color: {pal.apagado};")
        lay.addWidget(ico)
        lay.addWidget(hora, 1)
        lay.addWidget(dur)
        self.setToolTip(pagina.nome_do_alvo(s.tarefa_uuid))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def _menu(self, pos):
        m = QMenu(self)
        m.addAction("Apagar este registro", lambda: self.pagina.apagar_registro(self.s.uuid))
        m.exec(self.mapToGlobal(pos))


class PaginaFoco(QWidget):
    def __init__(self, janela, relogio_ms: int = 1000):
        super().__init__()
        self.janela = janela
        self.servico = janela.servico
        self.cron = Cronometro(self._config())
        self._titulo_original = None
        self._agora = datetime.now            # trocável nos testes
        self.alvo = ("livre", None, "Foco")
        self.registros: list[LinhaRegistro] = []
        pal = tema.atual

        lay = QHBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 12)
        lay.setSpacing(0)

        # ---- coluna do relógio ----
        esq_w = QWidget()
        esq = QVBoxLayout(esq_w)
        esq.setContentsMargins(0, 0, 24, 0)
        esq.setSpacing(12)
        topo = QHBoxLayout()
        titulo = QLabel("Pomodoro")
        titulo.setObjectName("titulo")
        titulo.setStyleSheet("font-size: 17px; font-weight: 700;")
        topo.addWidget(titulo)
        topo.addStretch(1)
        seg = QFrame()
        seg.setStyleSheet(f"QFrame {{ background: {pal.campo}; border-radius: 8px; }}")
        ls = QHBoxLayout(seg)
        ls.setContentsMargins(3, 3, 3, 3)
        ls.setSpacing(2)
        self.btn_pomodoro = QPushButton("Pomo")
        self.btn_cronometro = QPushButton("Cronômetro")
        for b in (self.btn_pomodoro, self.btn_cronometro):
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"QPushButton {{ background: transparent; border: none; border-radius: 6px; "
                            f"padding: 5px 12px; font-size: 12px; color: {pal.apagado}; }}"
                            f"QPushButton:checked {{ background: {pal.barra_ativa}; color: {pal.texto}; }}"
                            f"QPushButton:disabled {{ color: #555; }}")
            ls.addWidget(b)
        self.btn_pomodoro.setChecked(True)
        topo.addWidget(seg)
        topo.addStretch(1)
        self.btn_mais_registro = self._icone_plano("mais", "Adicionar foco manualmente")
        self.btn_menu = self._icone_plano("reticencias", "Ajustes do Pomodoro")
        topo.addWidget(self.btn_mais_registro)
        topo.addWidget(self.btn_menu)
        esq.addLayout(topo)
        esq.addStretch(1)
        self.btn_alvo = QPushButton("Foco")
        self.btn_alvo.setCursor(Qt.PointingHandCursor)
        self.btn_alvo.setStyleSheet(f"QPushButton {{ background: transparent; border: none; color: {pal.apagado}; "
                                    f"font-size: 12px; }} QPushButton:hover {{ color: {pal.texto}; border: none; }}")
        esq.addWidget(self.btn_alvo, 0, Qt.AlignHCenter)
        self.anel = AnelFoco()
        esq.addWidget(self.anel, 0, Qt.AlignHCenter)
        botoes = QHBoxLayout()
        botoes.setSpacing(10)
        botoes.addStretch(1)
        self.btn_iniciar = QPushButton("Começar")
        self.btn_pausar = QPushButton("Pausar")
        self.btn_parar = QPushButton("Parar")
        self.btn_pular = QPushButton("Pular pausa")
        for b in (self.btn_iniciar, self.btn_pausar, self.btn_parar, self.btn_pular):
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumWidth(110)
            botoes.addWidget(b)
        botoes.addStretch(1)
        self.btn_iniciar.setStyleSheet(f"QPushButton {{ background: {pal.destaque}; border: 1px solid "
                                       f"{pal.destaque}; color: {pal.sobre_destaque}; font-weight: 600; "
                                       f"border-radius: 16px; padding: 9px 28px; }} "
                                       f"QPushButton:disabled {{ background: {pal.campo}; border: 1px solid "
                                       f"{pal.borda}; color: {pal.apagado}; }}")
        esq.addLayout(botoes)
        esq.addStretch(2)
        lay.addWidget(esq_w, 5)

        # tarefa escolhida (mesma lista de antes, escondida: guarda o estado e serve de ponte)
        self.combo_tarefa = QComboBox(self)
        self.combo_tarefa.setVisible(False)

        # ajustes (aparecem pelo menu "...")
        self.painel_ajustes = Flutuante(self)
        form = QFormLayout(self.painel_ajustes)
        form.setContentsMargins(14, 12, 14, 12)
        form.setSpacing(8)
        c = self.cron.config
        self.s_foco = self._spin(1, 180, c.foco_min)
        self.s_curta = self._spin(1, 60, c.pausa_curta_min)
        self.s_longa = self._spin(1, 90, c.pausa_longa_min)
        self.s_ciclos = self._spin(1, 12, c.ciclos_ate_pausa_longa)
        form.addRow("Foco (min)", self.s_foco)
        form.addRow("Pausa curta (min)", self.s_curta)
        form.addRow("Pausa longa (min)", self.s_longa)
        form.addRow("Focos até a pausa longa", self.s_ciclos)
        self.painel_ajustes.hide()

        # ---- coluna da direita: visão geral e registros ----
        dir_w = QWidget()
        dir_ = QVBoxLayout(dir_w)
        dir_.setContentsMargins(24, 0, 0, 0)
        dir_.setSpacing(10)
        t1 = QLabel("Visão geral")
        t1.setStyleSheet("font-size: 14px; font-weight: 700;")
        dir_.addWidget(t1)
        grade = QFrame()
        gl = QVBoxLayout(grade)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(8)
        self.cartoes: dict[str, QLabel] = {}
        for linha in (("pomos_hoje", "Pomos de hoje", "foco_hoje", "Foco de hoje"),
                      ("pomos_total", "Pomos totais", "foco_total", "Duração Total Focada")):
            h = QHBoxLayout()
            h.setSpacing(8)
            for i in (0, 2):
                h.addWidget(self._cartao_numero(linha[i], linha[i + 1]))
            gl.addLayout(h)
        dir_.addWidget(grade)
        dir_.addSpacing(8)
        cab = QHBoxLayout()
        t2 = QLabel("Foco em Registrar")
        t2.setStyleSheet("font-size: 14px; font-weight: 700;")
        cab.addWidget(t2)
        cab.addStretch(1)
        self.btn_mais_registro2 = self._icone_plano("mais", "Adicionar foco manualmente")
        cab.addWidget(self.btn_mais_registro2)
        dir_.addLayout(cab)
        self.rolagem = QScrollArea()
        self.rolagem.setWidgetResizable(True)
        self.rolagem.setFrameShape(QScrollArea.NoFrame)
        self.rolagem.setStyleSheet("QScrollArea { background: transparent; } "
                                   "QScrollArea > QWidget > QWidget { background: transparent; }")
        self.miolo = QWidget()
        self.lay_reg = QVBoxLayout(self.miolo)
        self.lay_reg.setContentsMargins(0, 0, 6, 0)
        self.lay_reg.setSpacing(0)
        self.rolagem.setWidget(self.miolo)
        dir_.addWidget(self.rolagem, 1)
        dir_w.setMinimumWidth(320)
        dir_w.setMaximumWidth(420)
        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background: {pal.borda};")
        lay.addWidget(sep)
        lay.addWidget(dir_w, 3)

        self.btn_iniciar.clicked.connect(self.iniciar)
        self.btn_pausar.clicked.connect(self.alternar_pausa)
        self.btn_parar.clicked.connect(self.parar)
        self.btn_pular.clicked.connect(self.pular)
        self.btn_pomodoro.clicked.connect(lambda: self.definir_modo("pomodoro"))
        self.btn_cronometro.clicked.connect(lambda: self.definir_modo("cronometro"))
        self.btn_alvo.clicked.connect(self.abrir_seletor)
        self.btn_mais_registro.clicked.connect(self.adicionar_registro)
        self.btn_mais_registro2.clicked.connect(self.adicionar_registro)
        self.btn_menu.clicked.connect(self.abrir_ajustes)
        for s in (self.s_foco, self.s_curta, self.s_longa, self.s_ciclos):
            s.valueChanged.connect(self._mudou_config)
        self.relogio = QTimer(self)
        self.relogio.timeout.connect(lambda: self.tique())
        self.relogio.start(relogio_ms)
        self.atualizar()

    # ---- peças ----
    @staticmethod
    def _icone_plano(icone: str, dica: str) -> QPushButton:
        b = QPushButton()
        b.setObjectName("btnIcone")
        b.setIcon(icones.icone(icone, tema.atual.texto, 18))
        b.setIconSize(QSize(18, 18))
        b.setFixedSize(30, 30)
        b.setToolTip(dica)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _cartao_numero(self, chave: str, rotulo: str) -> QFrame:
        pal = tema.atual
        q = QFrame()
        q.setStyleSheet(f"QFrame {{ background: {pal.barra}; border-radius: 8px; }} QLabel {{ background: transparent; }}")
        v = QVBoxLayout(q)
        v.setContentsMargins(12, 9, 12, 9)
        v.setSpacing(2)
        a = QLabel(rotulo)
        a.setStyleSheet(f"font-size: 10px; color: {pal.apagado};")
        b = QLabel("0")
        b.setTextFormat(Qt.RichText)
        b.setStyleSheet("font-size: 20px;")
        v.addWidget(a)
        v.addWidget(b)
        self.cartoes[chave] = b
        return q

    @staticmethod
    def _spin(minimo, maximo, valor) -> QSpinBox:
        s = QSpinBox()
        s.setRange(minimo, maximo)
        s.setValue(valor)
        return s

    def _config(self) -> ConfigFoco:
        p = self.janela.prefs
        return ConfigFoco(int(p.get("foco_min", 25)), int(p.get("foco_pausa_curta", 5)),
                          int(p.get("foco_pausa_longa", 15)), int(p.get("foco_ciclos", 4)))

    def _mudou_config(self, *_):
        self.cron.config = ConfigFoco(self.s_foco.value(), self.s_curta.value(), self.s_longa.value(),
                                      self.s_ciclos.value())
        self.janela.prefs.update({"foco_min": self.s_foco.value(), "foco_pausa_curta": self.s_curta.value(),
                                  "foco_pausa_longa": self.s_longa.value(), "foco_ciclos": self.s_ciclos.value()})
        salvar = getattr(self.janela, "_ao_salvar_prefs", None)
        if salvar is not None:
            salvar(self.janela.prefs)
        self._desenhar()

    # ---- escolha do alvo ----
    def abrir_ajustes(self):
        self.painel_ajustes.mostrar_perto(self.btn_menu.mapToGlobal(self.btn_menu.rect().bottomLeft()))

    def abrir_seletor(self) -> SeletorFoco | None:
        if self.cron.ativo:
            return None
        sel = SeletorFoco(self, self)
        sel.mostrar_perto(self.btn_alvo.mapToGlobal(self.btn_alvo.rect().bottomLeft()))
        self.seletor = sel
        return sel

    def definir_alvo(self, tipo: str, valor, nome: str):
        """tipo: "livre", "tarefa" (valor = id) ou "habito" (valor = uuid do hábito)."""
        self.alvo = (tipo, valor, nome)
        self._recarregar_tarefas()
        if tipo == "tarefa":
            self.combo_tarefa.setCurrentIndex(max(self.combo_tarefa.findData(valor), 0))
        else:
            self.combo_tarefa.setCurrentIndex(0)
        self.btn_alvo.setText(f"{nome}  ›")

    def escolher_tarefa(self, tarefa_id: int | None):
        self._recarregar_tarefas()
        self.combo_tarefa.setCurrentIndex(max(self.combo_tarefa.findData(tarefa_id), 0))
        if tarefa_id is None:
            self.alvo = ("livre", None, "Foco")
        else:
            t = self.servico.banco.obter_tarefa(tarefa_id)
            self.alvo = ("tarefa", tarefa_id, t.titulo if t else "Foco")
        self.btn_alvo.setText(f"{self.alvo[2]}  ›" if self.alvo[0] != "livre" else "Foco  ›")

    def nome_do_alvo(self, uuid: str | None) -> str:
        if not uuid:
            return "Foco livre"
        for t in self.servico.banco.consultar("uuid = ?", (uuid,)):
            return t.titulo
        for h in self.servico.habitos.listar(None):
            if h.uuid == uuid:
                return h.nome
        return "Foco livre"

    # ---- comandos ----
    def definir_modo(self, modo: str):
        if self.cron.ativo:
            self.btn_pomodoro.setChecked(self.cron.modo == "pomodoro")
            self.btn_cronometro.setChecked(self.cron.modo == "cronometro")
            return
        self.cron.modo = modo
        self.btn_pomodoro.setChecked(modo == "pomodoro")
        self.btn_cronometro.setChecked(modo == "cronometro")
        self._desenhar()

    def iniciar(self):
        if self.cron.ativo:
            if self.cron.pausado:
                self.cron.retomar(self._agora())
            self._desenhar()
            return
        uuid = None
        if self.alvo[0] == "habito":
            uuid = self.alvo[1]
        else:
            tarefa_id = self.combo_tarefa.currentData()
            if tarefa_id is not None:
                t = self.servico.banco.obter_tarefa(tarefa_id)
                uuid = t.uuid if t else None
        self.cron.iniciar(self._agora(), uuid)
        self._desenhar()

    def alternar_pausa(self):
        if not self.cron.ativo:
            return
        if self.cron.pausado:
            self.cron.retomar(self._agora())
        else:
            self.cron.pausar(self._agora())
        self._desenhar()

    def parar(self):
        sessao = self.cron.parar(self._agora())
        if sessao is not None:
            self.servico.foco.registrar(sessao)
        self._desenhar()
        self.atualizar()

    def pular(self):
        self.cron.pular_pausa()
        self._desenhar()

    def encerrar(self):
        """Ao fechar o app: guarda o que estava em andamento."""
        if self.cron.ativo:
            self.parar()
        self._restaurar_titulo()

    def adicionar_registro(self):
        tarefas = [("Sem tarefa (foco livre)", None)]
        for t in self.servico.listar(TODAS):
            if not t.finalizada and not t.eh_nota:
                tarefas.append((t.titulo, t.uuid))
        dlg = DialogoRegistroFoco(self, tarefas[:300])
        if dlg.exec() == QDialog.Accepted:
            self.servico.foco.registrar(dlg.sessao())
            self.atualizar()

    def apagar_registro(self, uuid: str | None):
        if uuid:
            self.servico.foco.apagar(uuid)
            self.atualizar()

    def tique(self, agora: datetime | None = None):
        agora = agora or self._agora()
        for ev in self.cron.tick(agora):
            if ev.tipo == "foco_completo":
                self.servico.foco.registrar(ev.sessao)
                self.janela.notificador("Foco concluído", "Hora de uma pausa. Você mandou bem.")
                self.atualizar()
            else:
                self.janela.notificador("Pausa terminou", "Vamos para o próximo foco?")
        self._desenhar(agora)

    # ---- desenho ----
    def _recarregar_tarefas(self):
        atual = self.combo_tarefa.currentData()
        self.combo_tarefa.blockSignals(True)
        self.combo_tarefa.clear()
        self.combo_tarefa.addItem("Sem tarefa (foco livre)", None)
        for t in self.servico.listar(TODAS):
            self.combo_tarefa.addItem(t.titulo, t.id)
        self.combo_tarefa.setCurrentIndex(max(self.combo_tarefa.findData(atual), 0))
        self.combo_tarefa.blockSignals(False)

    def atualizar(self):
        """Recarrega a lista de tarefas, a visão geral e o registro de sessões."""
        if not self.cron.ativo:
            self._recarregar_tarefas()
        sessoes = self.servico.foco.sessoes()
        hoje = date.today()
        pomos = [s for s in sessoes if s.modo == "pomodoro" and s.completa]
        do_dia = [s for s in sessoes if s.inicio.date() == hoje]
        self.cartoes["pomos_hoje"].setText(str(sum(1 for s in pomos if s.inicio.date() == hoje)))
        self.cartoes["foco_hoje"].setText(_valor_com_unidades(sum(s.duracao_s for s in do_dia)))
        self.cartoes["pomos_total"].setText(str(len(pomos)))
        self.cartoes["foco_total"].setText(_valor_com_unidades(sum(s.duracao_s for s in sessoes)))
        while self.lay_reg.count():
            item = self.lay_reg.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.registros = []
        pal = tema.atual
        ultimo = None
        for s in sorted(sessoes, key=lambda x: x.inicio, reverse=True)[:300]:
            d = s.inicio.date()
            if d != ultimo:
                cab = QLabel(_nome_data(d))
                cab.setStyleSheet("font-size: 11px; font-weight: 700; padding: 10px 0 2px 0;")
                self.lay_reg.addWidget(cab)
                ultimo = d
            linha = LinhaRegistro(self, s)
            self.registros.append(linha)
            self.lay_reg.addWidget(linha)
        if not sessoes:
            vazio = QLabel("Nenhum foco registrado ainda.")
            vazio.setObjectName("mensagemVazia")
            self.lay_reg.addWidget(vazio)
        self.lay_reg.addStretch(1)
        self._desenhar()

    def _desenhar(self, agora: datetime | None = None):
        agora = agora or self._agora()
        c = self.cron
        pal = tema.atual
        cor = {c.FOCO: pal.destaque, c.PAUSA_CURTA: "#4dd0b1", c.PAUSA_LONGA: "#4dd0b1",
               c.PARADO: pal.apagado}[c.fase]
        crono = c.modo == "cronometro"
        if not c.ativo:
            total = None if crono else c.config.foco_min * 60
            texto = "00:00" if total is None else texto_relogio(total)
            self.anel.definir(1.0 if total else 0.0, texto, "", cor, tracos=crono)
        else:
            restante = c.restante(agora)
            decorrido = c.decorrido(agora)
            if restante is None:
                self.anel.definir((decorrido % 60) / 60, texto_relogio(decorrido),
                                  "Cronômetro" + (" (pausado)" if c.pausado else ""), cor, tracos=True)
            else:
                self.anel.definir(restante / c.total_s, texto_relogio(restante),
                                  NOMES_FASE[c.fase] + (" (pausado)" if c.pausado else ""), cor)
        self.btn_iniciar.setText("Retomar" if c.ativo and c.pausado else "Começar")
        self.btn_iniciar.setEnabled(not c.ativo or c.pausado)
        self.btn_pausar.setEnabled(c.ativo and not c.pausado)
        self.btn_parar.setEnabled(c.ativo)
        self.btn_pular.setEnabled(c.fase in (c.PAUSA_CURTA, c.PAUSA_LONGA))
        self.btn_iniciar.setVisible(not c.ativo or c.pausado)
        self.btn_pausar.setVisible(c.ativo and not c.pausado)
        self.btn_parar.setVisible(c.ativo)
        self.btn_pular.setVisible(c.fase in (c.PAUSA_CURTA, c.PAUSA_LONGA))
        self.btn_alvo.setEnabled(not c.ativo)
        self.combo_tarefa.setEnabled(not c.ativo)
        for w in (self.s_foco, self.s_curta, self.s_longa, self.s_ciclos):
            w.setEnabled(not c.ativo)
        self.btn_pomodoro.setEnabled(not c.ativo or c.modo == "pomodoro")
        self.btn_cronometro.setEnabled(not c.ativo or c.modo == "cronometro")
        if c.ativo:
            if self._titulo_original is None:
                self._titulo_original = self.janela.windowTitle()
            rest = c.restante(agora)
            valor = c.decorrido(agora) if rest is None else rest
            self.janela.setWindowTitle(f"{texto_relogio(valor)} · {NOMES_FASE.get(c.fase, 'Foco')}")
        else:
            self._restaurar_titulo()

    def _restaurar_titulo(self):
        if self._titulo_original is not None:
            self.janela.setWindowTitle(self._titulo_original)
            self._titulo_original = None
