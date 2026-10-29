"""Janela de Configurações: menu lateral com uma página por assunto. Tudo vale na hora, sem botão de salvar."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTime
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QCheckBox, QDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea,
                               QStackedWidget, QTimeEdit, QVBoxLayout, QWidget)

from .. import autostart
from ..marca import DESCRICAO, NOME, PASTA_DADOS, VERSAO
from . import estacoes, icones, tema

SECOES = [
    ("geral", "Geral", "engrenagem"),
    ("notificacoes", "Notificações", "sino"),
    ("data", "Data e hora", "relogio"),
    ("aparencia", "Aparência", "paleta"),
    ("ia", "Assistente de IA", "ia"),
    ("integracoes", "Integrações e dados", "plug"),
    ("atalhos", "Atalhos", "teclado"),
    ("sobre", "Sobre", "info"),
]


# ---------- peças ----------
class Interruptor(QAbstractButton):
    """Chave liga/desliga."""

    def __init__(self, ligado: bool = False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(ligado)
        self.setFixedSize(42, 24)
        self.setCursor(Qt.PointingHandCursor)

    def sizeHint(self):
        return QSize(42, 24)

    def paintEvent(self, _):
        pal = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal.destaque if self.isChecked() else pal.caixa))
        p.drawRoundedRect(QRectF(0, 1, 42, 22), 11, 11)
        p.setBrush(QColor("#ffffff"))
        x = 21 if self.isChecked() else 3
        p.drawEllipse(QRectF(x, 4, 18, 18))
        p.end()


def _rotulo(texto: str, nome: str = "", estilo: str = "") -> QLabel:
    r = QLabel(texto)
    r.setWordWrap(True)
    if nome:
        r.setObjectName(nome)
    if estilo:
        r.setStyleSheet(estilo)
    return r


class Grupo(QFrame):
    """Cartão arredondado com linhas separadas por um fio."""

    def __init__(self):
        super().__init__()
        self.setObjectName("grupoConfig")
        pal = tema.atual
        self.setStyleSheet(f"QFrame#grupoConfig {{ background: {pal.barra}; border-radius: 10px; }}"
                           f"QFrame#fioConfig {{ background: {pal.borda}; }}")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(18, 6, 18, 6)
        self.lay.setSpacing(0)
        self._n = 0

    def linha(self, titulo: str, descricao: str = "", controle: QWidget | None = None) -> QWidget:
        pal = tema.atual
        if self._n:
            fio = QFrame()
            fio.setObjectName("fioConfig")
            fio.setFixedHeight(1)
            self.lay.addWidget(fio)
        self._n += 1
        caixa = QWidget()
        h = QHBoxLayout(caixa)
        h.setContentsMargins(0, 12, 0, 12)
        h.setSpacing(16)
        v = QVBoxLayout()
        v.setSpacing(2)
        v.addWidget(_rotulo(titulo, "tituloLinha", "font-size: 14px; background: transparent;"))
        if descricao:
            v.addWidget(_rotulo(descricao, "descLinha", f"font-size: 12px; color: {pal.apagado}; background: transparent;"))
        h.addLayout(v, 1)
        if controle is not None:
            h.addWidget(controle, 0, Qt.AlignVCenter)
        self.lay.addWidget(caixa)
        return caixa


class AmostraCor(QAbstractButton):
    """Quadradinho que mostra como fica uma cor de tema."""

    def __init__(self, cor: tema.CorTema):
        super().__init__()
        self.cor = cor
        self.setCheckable(True)
        self.setFixedSize(88, 96)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(cor.nome)

    def paintEvent(self, _):
        pal = tema.atual
        amostra = tema.paleta(self.cor.chave, pal.escuro)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        area = QRectF(4, 4, 80, 64)
        p.setPen(QPen(QColor(amostra.borda), 1))
        p.setBrush(QColor(amostra.fundo))
        p.drawRoundedRect(area, 10, 10)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(amostra.barra))                       # a "barra lateral" em miniatura
        p.save()
        p.setClipRect(QRectF(area.left(), area.top(), 24, area.height()))
        p.drawRoundedRect(area, 10, 10)
        p.restore()
        p.setBrush(QColor(amostra.destaque))
        p.drawRoundedRect(QRectF(area.left() + 32, area.top() + 12, 34, 8), 4, 4)
        p.setBrush(QColor(amostra.apagado))
        p.drawRoundedRect(QRectF(area.left() + 32, area.top() + 28, 40, 5), 2.5, 2.5)
        p.drawRoundedRect(QRectF(area.left() + 32, area.top() + 40, 28, 5), 2.5, 2.5)
        if self.isChecked():
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(pal.destaque), 2.4))
            p.drawRoundedRect(area.adjusted(-2, -2, 2, 2), 12, 12)
        p.setPen(QColor(pal.destaque if self.isChecked() else pal.apagado))
        f = QFont(self.font())
        f.setPixelSize(12)
        p.setFont(f)
        p.drawText(QRectF(0, 72, 88, 20), Qt.AlignCenter, self.cor.nome)
        p.end()


class MiniaturaFundo(QAbstractButton):
    """Miniatura de um fundo ilustrado (ou do "sem fundo")."""

    def __init__(self, chave: str, nome: str):
        super().__init__()
        self.chave = chave
        self.nome = nome
        self.setCheckable(True)
        self.setFixedSize(140, 104)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(nome)

    def paintEvent(self, _):
        pal = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        area = QRectF(3, 3, 134, 76)
        if self.chave:
            from PySide6.QtGui import QPainterPath
            caminho = QPainterPath()
            caminho.addRoundedRect(area, 10, 10)
            p.save()
            p.setClipPath(caminho)
            estacoes.pintar(p, area, self.chave, pal.escuro, com_ceu=True)
            p.restore()
        else:
            p.setPen(QPen(QColor(pal.borda), 1))
            p.setBrush(QColor(pal.fundo))
            p.drawRoundedRect(area, 10, 10)
            p.setPen(QColor(pal.apagado))
            p.drawText(area, Qt.AlignCenter, "Sem fundo")
        if self.isChecked():
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(pal.destaque), 2.4))
            p.drawRoundedRect(area.adjusted(-2, -2, 2, 2), 12, 12)
        p.setPen(QColor(pal.destaque if self.isChecked() else pal.apagado))
        f = QFont(self.font())
        f.setPixelSize(12)
        p.setFont(f)
        p.drawText(QRectF(0, 82, 140, 20), Qt.AlignCenter, self.nome)
        p.end()


def _titulo_secao(texto: str) -> QLabel:
    pal = tema.atual
    r = QLabel(texto)
    r.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {pal.texto}; background: transparent; padding: 14px 2px 8px 2px;")
    return r


# ---------- a janela ----------
class JanelaConfiguracoes(QDialog):
    def __init__(self, janela, secao: str = ""):
        super().__init__(janela)
        self.janela = janela
        self.setWindowTitle("Configurações")
        self.setObjectName("configuracoes")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumSize(820, 540)
        self.resize(1060, 680)
        pal = tema.atual
        self.setStyleSheet(f"QDialog#configuracoes {{ background: {pal.fundo}; }}")

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        coluna = QWidget()
        coluna.setObjectName("colunaConfig")
        coluna.setAttribute(Qt.WA_StyledBackground, True)
        coluna.setFixedWidth(232)
        coluna.setStyleSheet(f"QWidget#colunaConfig {{ background: {pal.barra}; }}")
        lc = QVBoxLayout(coluna)
        lc.setContentsMargins(14, 20, 14, 14)
        lc.setSpacing(10)
        titulo = QLabel("Configurações")
        titulo.setStyleSheet("font-size: 18px; font-weight: 700; background: transparent; padding-left: 8px;")
        lc.addWidget(titulo)
        self.nav = QListWidget()
        self.nav.setObjectName("navConfig")
        self.nav.setFocusPolicy(Qt.NoFocus)
        self.nav.setIconSize(QSize(20, 20))
        self.nav.setStyleSheet(
            f"QListWidget#navConfig {{ background: transparent; border: none; outline: none; }}"
            f"QListWidget#navConfig::item {{ padding: 10px 12px; border-radius: 8px; margin: 1px 0; }}"
            f"QListWidget#navConfig::item:hover {{ background: {pal.barra_hover}; }}"
            f"QListWidget#navConfig::item:selected {{ background: {pal.barra_ativa}; color: {pal.texto}; }}")
        for chave, nome, icone in SECOES:
            it = QListWidgetItem(nome)
            it.setData(Qt.UserRole, chave)
            self.nav.addItem(it)
        lc.addWidget(self.nav, 1)
        raiz.addWidget(coluna)

        self.pilha = QStackedWidget()
        self.paginas: dict[str, QWidget] = {}
        construtores = {
            "geral": self._pagina_geral, "notificacoes": self._pagina_notificacoes, "data": self._pagina_data,
            "aparencia": self._pagina_aparencia, "ia": self._pagina_ia, "integracoes": self._pagina_integracoes,
            "atalhos": self._pagina_atalhos, "sobre": self._pagina_sobre}
        for chave, nome, _ in SECOES:
            corpo = QWidget()
            lay = QVBoxLayout(corpo)
            lay.setContentsMargins(34, 26, 34, 26)
            lay.setSpacing(10)
            cab = QLabel(nome)
            cab.setStyleSheet("font-size: 22px; font-weight: 700; background: transparent;")
            lay.addWidget(cab)
            construtores[chave](lay)
            lay.addStretch(1)
            rolagem = QScrollArea()
            rolagem.setWidgetResizable(True)
            rolagem.setFrameShape(QFrame.NoFrame)
            rolagem.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }")
            rolagem.setWidget(corpo)
            self.pilha.addWidget(rolagem)
            self.paginas[chave] = rolagem
        raiz.addWidget(self.pilha, 1)

        self.nav.currentRowChanged.connect(self.pilha.setCurrentIndex)
        self._icones_da_navegacao()
        chaves = [c for c, _, _ in SECOES]
        self.nav.setCurrentRow(chaves.index(secao) if secao in chaves else 0)

    # ---- utilitários ----
    @property
    def prefs(self) -> dict:
        return self.janela.prefs

    def _icones_da_navegacao(self):
        pal = tema.atual
        for i, (_, _, icone) in enumerate(SECOES):
            self.nav.item(i).setIcon(icones.icone(icone, pal.texto_barra, 20))

    def mostrar_secao(self, chave: str):
        chaves = [c for c, _, _ in SECOES]
        if chave in chaves:
            self.nav.setCurrentRow(chaves.index(chave))

    def _guardar(self, **novas):
        self.janela.aplicar_preferencias(novas)
        self._icones_da_navegacao()

    def _interruptor(self, chave: str, padrao: bool) -> Interruptor:
        s = Interruptor(bool(self.prefs.get(chave, padrao)))
        s.toggled.connect(lambda v, c=chave: self._guardar(**{c: bool(v)}))
        return s

    # ---- páginas ----
    def _pagina_geral(self, lay: QVBoxLayout):
        g = Grupo()
        self.campo_nome = QLineEdit(str(self.prefs.get("nome_usuario") or ""))
        self.campo_nome.setPlaceholderText("Seu nome")
        self.campo_nome.setFixedWidth(200)
        self.campo_nome.editingFinished.connect(self._nome_mudou)
        g.linha("Seu nome", "A inicial aparece no círculo do canto superior esquerdo.", self.campo_nome)
        self.sw_bandeja = self._interruptor("fechar_para_bandeja", True)
        g.linha("Continuar rodando ao fechar a janela",
                "O app fica perto do relógio, para os lembretes continuarem tocando.", self.sw_bandeja)
        self.sw_iniciar = Interruptor(bool(self.prefs.get("iniciar_com_windows", False)))
        self.sw_iniciar.toggled.connect(lambda v: self._guardar(iniciar_com_windows=bool(v)))
        if autostart.disponivel():
            g.linha("Abrir junto com o Windows", "Começa minimizado, sem abrir a janela.", self.sw_iniciar)
        self.sw_lateral = Interruptor(bool(self.janela.bool_lateral()))
        self.sw_lateral.toggled.connect(lambda v: self.janela.definir_detalhe_lateral(bool(v)))
        g.linha("Painel lateral de detalhes", "Em vez do cartão flutuante, a tarefa abre num painel fixo à direita.",
                self.sw_lateral)
        lay.addWidget(g)

    def _nome_mudou(self):
        nome = self.campo_nome.text().strip()
        self._guardar(nome_usuario=nome)
        self.janela.btn_avatar.setIcon(self.janela._icone_avatar(nome or "G"))

    def _pagina_notificacoes(self, lay: QVBoxLayout):
        g = Grupo()
        self.sw_aviso = self._interruptor("aviso_na_tela", True)
        g.linha("Janelinha de lembrete", "Mostra a janelinha com os botões Adiar e Concluir.", self.sw_aviso)
        self.sw_resumo = self._interruptor("resumo_diario", True)
        g.linha("Resumo do dia", "Uma notificação com o que está marcado para hoje.", self.sw_resumo)
        self.hora_resumo = QTimeEdit()
        self.hora_resumo.setDisplayFormat("HH:mm")
        self.hora_resumo.setFixedWidth(90)
        h, m = (int(x) for x in str(self.prefs.get("resumo_hora", "08:00")).split(":"))
        self.hora_resumo.setTime(QTime(h, m))
        self.hora_resumo.timeChanged.connect(lambda t: self._guardar(resumo_hora=t.toString("HH:mm")))
        g.linha("Horário do resumo", "O aviso aparece a partir deste horário.", self.hora_resumo)
        lay.addWidget(g)

    def _pagina_data(self, lay: QVBoxLayout):
        g = Grupo()
        self.sw_segunda = self._interruptor("semana_comeca_segunda", False)
        g.linha("A semana começa na segunda-feira", "Vale para as grades do calendário. Desligado, começa no domingo.",
                self.sw_segunda)
        lay.addWidget(g)

    def _pagina_aparencia(self, lay: QVBoxLayout):
        lay.addWidget(_titulo_secao("Modo"))
        barra = QFrame()
        barra.setObjectName("segmentos")
        pal = tema.atual
        barra.setStyleSheet(
            f"QFrame#segmentos {{ background: {pal.barra}; border-radius: 10px; }}"
            f"QPushButton#seg {{ background: transparent; border: none; border-radius: 8px; padding: 8px 20px; }}"
            f"QPushButton#seg:checked {{ background: {pal.destaque}; color: {pal.sobre_destaque}; font-weight: 600; }}")
        hl = QHBoxLayout(barra)
        hl.setContentsMargins(4, 4, 4, 4)
        hl.setSpacing(2)
        self.grupo_modo = QButtonGroup(self)
        self.btns_modo: dict[str, QPushButton] = {}
        atual = self.prefs.get("tema_modo") or tema.MODO_PADRAO
        for chave, nome in tema.MODOS:
            b = QPushButton(nome)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setChecked(chave == atual)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=chave: self._escolher_modo(c))
            self.grupo_modo.addButton(b)
            self.btns_modo[chave] = b
            hl.addWidget(b)
        topo = QHBoxLayout()
        topo.addWidget(barra)
        topo.addStretch(1)
        lay.addLayout(topo)

        lay.addWidget(_titulo_secao("Cor do tema"))
        grade = QGridLayout()
        grade.setHorizontalSpacing(8)
        grade.setVerticalSpacing(6)
        self.amostras: dict[str, AmostraCor] = {}
        escolhida = self.prefs.get("tema_cor") or tema.COR_PADRAO
        for i, c in enumerate(tema.CORES):
            a = AmostraCor(c)
            a.setChecked(c.chave == escolhida)
            a.clicked.connect(lambda _=False, k=c.chave: self._escolher_cor(k))
            self.amostras[c.chave] = a
            grade.addWidget(a, i // 6, i % 6)
        grade.setColumnStretch(6, 1)
        lay.addLayout(grade)

        lay.addWidget(_titulo_secao("Fundo ilustrado"))
        grade2 = QGridLayout()
        grade2.setHorizontalSpacing(10)
        grade2.setVerticalSpacing(6)
        self.miniaturas: dict[str, MiniaturaFundo] = {}
        atual_fundo = self.prefs.get("tema_fundo") or ""
        for i, (chave, nome) in enumerate([("", "Sem fundo"), *estacoes.ESTACOES]):
            m = MiniaturaFundo(chave, nome)
            m.setChecked(chave == atual_fundo)
            m.clicked.connect(lambda _=False, k=chave: self._escolher_fundo(k))
            self.miniaturas[chave] = m
            grade2.addWidget(m, i // 5, i % 5)
        grade2.setColumnStretch(5, 1)
        lay.addLayout(grade2)

    def _escolher_modo(self, modo: str):
        self._guardar(tema_modo=modo)
        self._marcar_aparencia()

    def _escolher_cor(self, cor: str):
        self._guardar(tema_cor=cor)
        self._marcar_aparencia()

    def _escolher_fundo(self, fundo: str):
        self._guardar(tema_fundo=fundo)
        self._marcar_aparencia()

    def _marcar_aparencia(self):
        modo = self.prefs.get("tema_modo") or tema.MODO_PADRAO
        for k, b in self.btns_modo.items():
            b.setChecked(k == modo)
        cor = self.prefs.get("tema_cor") or tema.COR_PADRAO
        for k, a in self.amostras.items():
            a.setChecked(k == cor)
            a.update()
        fundo = self.prefs.get("tema_fundo") or ""
        for k, m in self.miniaturas.items():
            m.setChecked(k == fundo)
            m.update()

    def _pagina_ia(self, lay: QVBoxLayout):
        g = Grupo()
        b = QPushButton("Abrir")
        b.clicked.connect(self.janela.abrir_config_ia)
        g.linha("Provedor, chave de API e voz",
                "Escolha Gemini, Claude, ChatGPT ou DeepSeek, cole a sua chave e defina quem transcreve a sua voz. "
                "A chave fica guardada só neste computador.", b)
        lay.addWidget(g)
        lay.addWidget(_rotulo("A IA só propõe mudanças. Nada é alterado até você clicar em Aplicar, e dá para desfazer.",
                              "", f"color: {tema.atual.apagado}; font-size: 12px; background: transparent; padding: 6px 2px;"))

    def _pagina_integracoes(self, lay: QVBoxLayout):
        g = Grupo()
        b1 = QPushButton("Abrir")
        b1.clicked.connect(self.janela.abrir_integracoes)
        g.linha("Google Calendar e calendários por link", "Traga eventos de fora para a sua agenda.", b1)
        b2 = QPushButton("Configurar")
        b2.clicked.connect(self.janela.configurar_sincronizacao)
        g.linha("Sincronizar entre aparelhos", "Use o seu próprio servidor para manter vários computadores iguais.", b2)
        b3 = QPushButton("Abrir")
        b3.clicked.connect(self.janela.abrir_dados)
        g.linha("Backup, importar e exportar", "Salve uma cópia dos seus dados ou traga de outro app.", b3)
        lay.addWidget(g)

    def _pagina_atalhos(self, lay: QVBoxLayout):
        from .janela import ATALHOS
        pal = tema.atual
        g = Grupo()
        for tecla, descricao in ATALHOS:
            etiqueta = QLabel(tecla)
            etiqueta.setStyleSheet(f"background: {pal.campo}; border-radius: 6px; padding: 4px 10px; font-size: 12px; "
                                   f"font-weight: 600;")
            g.linha(descricao, "", etiqueta)
        lay.addWidget(g)

    def _pagina_sobre(self, lay: QVBoxLayout):
        pal = tema.atual
        g = Grupo()
        g.linha(NOME, f"Versão {VERSAO}")
        g.linha("Para que serve", DESCRICAO)
        g.linha("Autoria", "Feito por Gilson Tavares da Silva para a LIA, a Liga de Inteligência Artificial da Unicamp.")
        g.linha("Seus dados", f"Ficam só neste computador, na pasta {PASTA_DADOS} dentro da sua pasta de usuário.")
        g.linha("Licença", "Todos os direitos reservados.")
        lay.addWidget(g)
