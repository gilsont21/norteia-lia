"""Janela principal: coluna de ícones, barra lateral, lista de tarefas e painel de detalhe."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from PySide6.QtCore import (QCoreApplication, QDate, QObject, QRect, QRunnable, QSize, QThreadPool, QTime, QTimer, Qt,
                            QUrl, Signal)
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QCursor, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QDateEdit, QFileDialog, QFrame, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QStackedLayout, QStackedWidget, QSystemTrayIcon,
                               QTimeEdit, QToolTip, QVBoxLayout, QWidget, QCheckBox, QDialog)

from ..core import (AMANHA, CAIXA, CONCLUIDAS, HOJE, LIXEIRA, PROXIMOS, TODAS, Prioridade, Servico,
                    Tarefa, chave_filtro, chave_tag, recorrencia)
from ..core import lembretes as lembretes_core
from ..core.servico import MAX_NIVEIS, PREFIXO_FILTRO, PREFIXO_TAG
from .. import autostart
from ..marca import NOME
from . import icones, tema
from .aviso import OPCOES_SONECA, GerenteAvisos
from ..core import ia, ia_provedores
from ..core.foco import formatar_duracao
from .atalho_global import JanelaRapida
from .busca_flutuante import PainelBusca
from .dialogo_google import DialogoGoogle, DialogoIntegracoes, GerenteGoogle
from .dialogo_lista import SEM_COR, DialogoLista
from .dialogos import (DialogoAssinaturas, DialogoConfiguracoes, DialogoDados, DialogoFiltro, DialogoRepeticao,
                       DialogoSincronizacao)
from .pagina_calendario import PaginaCalendario
from .popovers import CartaoTarefa
from .pagina_extras import PaginaContagem, PaginaEstatisticas
from .pagina_foco import PaginaFoco
from .pagina_habitos import PaginaHabitos
from .pagina_ia import DialogoIA, PaginaIA
from .pagina_quadros import PaginaMatriz, VistaKanban, VistaLinhaTempo
from .delegados import (PAPEL_CHAVE, PAPEL_COR, PAPEL_CONTAGEM, PAPEL_EMOJI, PAPEL_ICONE,
                        PAPEL_ROTULO_ICONE, PAPEL_TAREFA, PAPEL_TIPO, DelegadoBarra,
                        DelegadoTarefa, area_caixa)

BUSCA = "busca"
TITULOS = {
    TODAS: "Todas", HOJE: "Hoje", AMANHA: "Amanhã", PROXIMOS: "Próximos 7 dias", CAIXA: "Caixa de Entrada",
    CONCLUIDAS: "Concluídas", LIXEIRA: "Lixeira", BUSCA: "Busca",
}
CORES_LISTAS = ["#f0524a", "#f5a623", "#4dd0b1", "#4772fa", "#b57edc", "#e8e8e8"]
ORDENS = [("data", "Data"), ("prioridade", "Prioridade"), ("titulo", "Título"),
          ("criacao", "Mais recentes"), ("manual", "Manual (arraste as tarefas)")]
AGRUPAMENTOS = [("nenhum", "Sem agrupamento"), ("data", "Data"), ("projeto", "Lista"),
                ("prioridade", "Prioridade"), ("etiqueta", "Etiqueta")]
GRUPOS_DE_DATA = ["Atrasadas", "Hoje", "Amanhã", "Próximos 7 dias", "Mais tarde", "Sem data"]
INSISTIR = [("Desligado", 0), ("A cada 5 minutos", 5), ("A cada 10 minutos", 10),
            ("A cada 15 minutos", 15), ("A cada 30 minutos", 30)]
ATALHOS = [
    ("Ctrl+N", "Nova tarefa"), ("Ctrl+F ou Ctrl+K", "Buscar"), ("Ctrl+B", "Mostrar ou esconder a barra lateral"),
    ("Ctrl+Enter", "Concluir ou reabrir a tarefa selecionada"), ("Ctrl+D", "Duplicar a tarefa selecionada"),
    ("Ctrl+P", "Fixar ou desafixar a tarefa selecionada"), ("Delete", "Mover a tarefa para a lixeira"),
    ("Ctrl+Alt+N (global)", "Nova tarefa rápida, mesmo com o app na bandeja (Windows)"),
    ("Ctrl+1 a Ctrl+8", "Tarefas, Calendário, Matriz, Foco, Hábitos, Contagem, Estatísticas, Assistente de IA"),
    ("F5", "Sincronizar agora"), ("Ctrl+,", "Configurações"), ("F1", "Esta lista"),
]
PAGINAS = [          # (chave, ícone, dica) na ordem da coluna de ícones
    ("tarefas", "tarefas", "Tarefas"),
    ("calendario", "calendario", "Calendário"),
    ("matriz", "matriz", "Matriz de Eisenhower"),
    ("foco", "foco", "Foco e Pomodoro"),
    ("habitos", "habitos", "Hábitos"),
    ("contagem", "contagem", "Contagem regressiva"),
    ("estatisticas", "estatisticas", "Estatísticas"),
    ("ia", "ia", "Assistente de IA"),
]
SECUNDARIAS = ("contagem", "estatisticas")      # só aparecem no menu "…" da barra de ícones
PAGINAS_SEM_LATERAIS = ("foco", "habitos", "contagem", "estatisticas", "ia")   # escondem barra lateral e detalhe
PAGINAS_SEM_DETALHE = PAGINAS_SEM_LATERAIS + ("calendario",)
VISOES = [("lista", "Lista"), ("kanban", "Kanban"), ("linha_tempo", "Linha do tempo")]
DURACOES = [("Padrão (1 h)", 0), ("15 min", 15), ("30 min", 30), ("45 min", 45), ("1 h", 60), ("1 h 30", 90),
            ("2 h", 120), ("3 h", 180), ("4 h", 240)]
PERSONALIZAR = "__personalizar__"


class _SinaisSync(QObject):
    pronto = Signal(object, object)   # (resposta, erro)


class _SinaisIA(QObject):
    pronto = Signal(int, object, object)   # (tarefa, subtarefas, erro)


class _TrabalhoIA(QRunnable):
    def __init__(self, tarefa_id: int, funcao, sinais: _SinaisIA):
        super().__init__()
        self.tarefa_id, self.funcao, self.sinais = tarefa_id, funcao, sinais

    def run(self):
        try:
            self.sinais.pronto.emit(self.tarefa_id, self.funcao(), None)
        except Exception as e:  # noqa: BLE001
            self.sinais.pronto.emit(self.tarefa_id, None, e)


class _EnvioSync(QRunnable):
    """Faz só a parte de rede, fora da thread da tela (o banco não é tocado aqui)."""

    def __init__(self, funcao, sinais: _SinaisSync):
        super().__init__()
        self.funcao, self.sinais = funcao, sinais

    def run(self):
        try:
            self.sinais.pronto.emit(self.funcao(), None)
        except Exception as e:  # noqa: BLE001 - qualquer falha de rede vira aviso na tela
            self.sinais.pronto.emit(None, e)


class ListaTarefas(QListWidget):
    """Lista que avisa quando o círculo de conclusão é clicado."""

    clicou_tarefa = Signal(int, object)   # clique (sem arrastar) numa linha: id e retângulo dela na tela

    def __init__(self, ao_alternar):
        super().__init__()
        self._ao_alternar = ao_alternar
        self._toque = None
        self.setObjectName("tarefas")
        self.setMouseTracking(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def permitir_arrastar(self, sim: bool):
        self.setDragDropMode(QAbstractItemView.InternalMove if sim else QAbstractItemView.NoDragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragEnabled(sim)

    def mousePressEvent(self, e):
        item = self.itemAt(e.position().toPoint())
        if item is not None and e.button() == Qt.LeftButton and item.data(PAPEL_TAREFA) is not None:
            linha = self.visualItemRect(item)
            if area_caixa(linha).adjusted(-6, -6, 6, 6).contains(e.position().toPoint()):
                self._ao_alternar(item.data(PAPEL_TAREFA).id)
                return
        dado = item.data(PAPEL_TAREFA) if item is not None else None
        self._toque = (dado.id, e.position().toPoint()) if (dado is not None and e.button() == Qt.LeftButton) else None
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.mousePressEvent(e)           # o 2º clique de um duplo clique conta como um clique normal

    def mouseReleaseEvent(self, e):
        toque, self._toque = self._toque, None
        super().mouseReleaseEvent(e)
        if toque is None or e.button() != Qt.LeftButton:
            return
        pos = e.position().toPoint()
        if (pos - toque[1]).manhattanLength() > 6:
            return
        item = self.itemAt(pos)
        dado = item.data(PAPEL_TAREFA) if item is not None else None
        if dado is not None and dado.id == toque[0]:
            r = self.visualItemRect(item)
            self.clicou_tarefa.emit(dado.id, QRect(self.viewport().mapToGlobal(r.topLeft()), r.size()))


class PainelDetalhe(QWidget):
    def __init__(self, janela: "JanelaPrincipal"):
        super().__init__()
        self.setObjectName("detalhe")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.janela = janela
        self.tarefa: Tarefa | None = None
        self._carregando = False
        self._alvo_sub: int | None = None      # onde a próxima subtarefa será criada (None = a tarefa aberta)
        self._tarefa_aberta_id: int | None = None
        self._regra_atual: str | None = None
        self.setMinimumWidth(360)
        self.setMaximumWidth(420)

        pilha = QStackedLayout(self)
        vazio = QLabel("Selecione uma tarefa\npara ver os detalhes")
        vazio.setAlignment(Qt.AlignCenter)
        vazio.setObjectName("mensagemVazia")
        pilha.addWidget(vazio)

        corpo = QWidget()
        corpo.setObjectName("corpoDetalhe")
        corpo.setStyleSheet("QWidget#corpoDetalhe { background: transparent; }")
        lay = QVBoxLayout(corpo)
        lay.setContentsMargins(24, 24, 20, 20)
        lay.setSpacing(6)

        self.titulo = QLineEdit()
        self.titulo.setObjectName("tituloTarefa")
        self.titulo.setPlaceholderText("Título da tarefa")
        lay.addWidget(self.titulo)

        lay.addSpacing(8)
        lay.addWidget(self._rotulo("PRAZO"))
        linha_prazo = QHBoxLayout()
        self.tem_prazo = QCheckBox("Definir")
        self.prazo = QDateEdit()
        self.prazo.setCalendarPopup(True)
        self.prazo.setDisplayFormat("dd/MM/yyyy")
        linha_prazo.addWidget(self.tem_prazo)
        linha_prazo.addWidget(self.prazo, 1)
        lay.addLayout(linha_prazo)

        linha_inicio = QHBoxLayout()
        self.tem_inicio = QCheckBox("Começa em")
        self.inicio = QDateEdit()
        self.inicio.setCalendarPopup(True)
        self.inicio.setDisplayFormat("dd/MM/yyyy")
        self.inicio.setToolTip("Para tarefas de vários dias: o prazo vira o último dia")
        linha_inicio.addWidget(self.tem_inicio)
        linha_inicio.addWidget(self.inicio, 1)
        lay.addLayout(linha_inicio)

        linha_hora = QHBoxLayout()
        self.tem_hora = QCheckBox("Com hora")
        self.hora = QTimeEdit()
        self.hora.setDisplayFormat("HH:mm")
        linha_hora.addWidget(self.tem_hora)
        linha_hora.addWidget(self.hora, 1)
        lay.addLayout(linha_hora)

        linha_dur = QHBoxLayout()
        rot_dur = QLabel("Duração")
        self.duracao = QComboBox()
        for nome, valor in DURACOES:
            self.duracao.addItem(nome, valor)
        self.duracao.setToolTip("Quanto espaço a tarefa ocupa no calendário")
        linha_dur.addWidget(rot_dur)
        linha_dur.addWidget(self.duracao, 1)
        lay.addLayout(linha_dur)

        lay.addWidget(self._rotulo("REPETIR"))
        self.repetir = QComboBox()
        lay.addWidget(self.repetir)

        lay.addWidget(self._rotulo("LEMBRAR"))
        self.lembrar = QComboBox()
        lay.addWidget(self.lembrar)

        lay.addWidget(self._rotulo("LEMBRETE CONSTANTE"))
        self.constante = QComboBox()
        for nome, valor in INSISTIR:
            self.constante.addItem(nome, valor)
        self.constante.setToolTip("Repete o aviso até você concluir a tarefa (por até 24 horas)")
        lay.addWidget(self.constante)

        lay.addWidget(self._rotulo("PRIORIDADE"))
        self.prioridade = QComboBox()
        for valor in range(4):
            self.prioridade.addItem(tema.NOME_PRIORIDADE[valor], valor)
        lay.addWidget(self.prioridade)

        lay.addWidget(self._rotulo("PROJETO"))
        self.projeto = QComboBox()
        lay.addWidget(self.projeto)

        lay.addWidget(self._rotulo("SEÇÃO E TIPO"))
        linha_sec = QHBoxLayout()
        self.secao = QComboBox()
        self.secao.setEditable(True)
        self.secao.lineEdit().setPlaceholderText("Seção (Kanban)")
        self.tipo = QComboBox()
        self.tipo.addItem("Tarefa", "tarefa")
        self.tipo.addItem("Nota", "nota")
        linha_sec.addWidget(self.secao, 1)
        linha_sec.addWidget(self.tipo)
        lay.addLayout(linha_sec)

        lay.addWidget(self._rotulo("TAGS"))
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("separe por espaço: casa estudo")
        lay.addWidget(self.tags)

        self.rot_subs = self._rotulo("SUBTAREFAS")
        lay.addWidget(self.rot_subs)
        self.subs_caixa = QVBoxLayout()
        self.subs_caixa.setSpacing(2)
        lay.addLayout(self.subs_caixa)
        self.nova_sub = QLineEdit()
        self.nova_sub.setPlaceholderText("+  Adicionar subtarefa e apertar Enter")
        lay.addWidget(self.nova_sub)
        self.btn_ia = QPushButton("Sugerir subtarefas com IA")
        self.btn_ia.setCursor(Qt.PointingHandCursor)
        self.btn_ia.setToolTip("Envia só o título e as notas desta tarefa para a IA escolhida (precisa de chave "
                               "em Configurações de IA)")
        lay.addWidget(self.btn_ia)

        lay.addWidget(self._rotulo("NOTAS"))
        self.notas = QPlainTextEdit()
        self.notas.setPlaceholderText("Escreva detalhes, links, ideias...")
        self.notas.setMinimumHeight(110)
        lay.addWidget(self.notas, 1)

        self.rot_coment = self._rotulo("COMENTÁRIOS")
        lay.addWidget(self.rot_coment)
        self.coment_caixa = QVBoxLayout()
        self.coment_caixa.setSpacing(4)
        lay.addLayout(self.coment_caixa)
        self.novo_coment = QLineEdit()
        self.novo_coment.setPlaceholderText("+  Comentar e apertar Enter")
        lay.addWidget(self.novo_coment)

        self.rot_anexos = self._rotulo("ANEXOS")
        lay.addWidget(self.rot_anexos)
        self.anexos_caixa = QVBoxLayout()
        self.anexos_caixa.setSpacing(2)
        lay.addLayout(self.anexos_caixa)
        self.btn_anexar = QPushButton("+  Adicionar arquivo")
        self.btn_anexar.setCursor(Qt.PointingHandCursor)
        lay.addWidget(self.btn_anexar)

        self.rot_foco = QLabel("")
        self.rot_foco.setObjectName("mensagemVazia")
        lay.addWidget(self.rot_foco)
        acoes = QHBoxLayout()
        acoes.setSpacing(6)
        self.btn_foco = QPushButton("Foco")
        self.btn_fixar = QPushButton("Fixar")
        self.btn_duplicar = QPushButton("Duplicar")
        self.btn_descartar = QPushButton("Não será feito")
        self.btn_modelo = QPushButton("Salvar como modelo")
        for b in (self.btn_foco, self.btn_fixar, self.btn_duplicar):
            b.setCursor(Qt.PointingHandCursor)
            acoes.addWidget(b)
        lay.addLayout(acoes)
        acoes2 = QHBoxLayout()
        acoes2.setSpacing(6)
        for b in (self.btn_descartar, self.btn_modelo):
            b.setCursor(Qt.PointingHandCursor)
            acoes2.addWidget(b)
        lay.addLayout(acoes2)
        botoes = QHBoxLayout()
        self.btn_apagar = QPushButton("Mover para a lixeira")
        self.btn_apagar.setObjectName("perigo")
        botoes.addWidget(self.btn_apagar)
        botoes.addStretch(1)
        lay.addLayout(botoes)
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QScrollArea.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rolagem.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        rolagem.setWidget(corpo)
        self.rolagem = rolagem
        pilha.addWidget(rolagem)
        self.pilha = pilha
        pilha.setCurrentIndex(0)

        self.titulo.editingFinished.connect(self._salvar)
        self.tem_prazo.toggled.connect(self._salvar)
        self.prazo.dateChanged.connect(self._salvar)
        self.tem_hora.toggled.connect(self._salvar)
        self.hora.timeChanged.connect(self._salvar)
        self.repetir.currentIndexChanged.connect(self._ao_trocar_repetir)
        self.tem_inicio.toggled.connect(self._salvar)
        self.inicio.dateChanged.connect(self._salvar)
        self.duracao.currentIndexChanged.connect(self._salvar)
        self.secao.lineEdit().editingFinished.connect(self._salvar)
        self.secao.activated.connect(self._salvar)
        self.tipo.currentIndexChanged.connect(self._salvar)
        self.novo_coment.returnPressed.connect(self._adicionar_comentario)
        self.btn_anexar.clicked.connect(lambda: self.anexar())
        self.btn_ia.clicked.connect(lambda: self.tarefa and self.janela.sugerir_subtarefas(self.tarefa.id))
        self.btn_foco.clicked.connect(lambda: self.tarefa and self.janela.iniciar_foco_na_tarefa(self.tarefa.id))
        self.btn_modelo.clicked.connect(lambda: self.tarefa and self.janela.salvar_modelo(self.tarefa.id))
        self.lembrar.currentIndexChanged.connect(self._salvar)
        self.constante.currentIndexChanged.connect(self._salvar)
        self.btn_fixar.clicked.connect(lambda: self.tarefa and self.janela.fixar_tarefa(self.tarefa.id))
        self.btn_duplicar.clicked.connect(lambda: self.tarefa and self.janela.duplicar_tarefa(self.tarefa.id))
        self.btn_descartar.clicked.connect(lambda: self.tarefa and self.janela.descartar_tarefa(self.tarefa.id))
        self.prioridade.currentIndexChanged.connect(self._salvar)
        self.projeto.currentIndexChanged.connect(self._salvar)
        self.tags.editingFinished.connect(self._salvar)
        self.notas.textChanged.connect(self._salvar)
        self.btn_apagar.clicked.connect(self._apagar)
        self.nova_sub.returnPressed.connect(self._adicionar_sub)

    @staticmethod
    def _rotulo(texto: str) -> QLabel:
        rot = QLabel(texto)
        rot.setObjectName("secao")
        rot.setContentsMargins(0, 10, 0, 2)
        return rot

    def mostrar(self, tarefa: Tarefa | None):
        self.tarefa = tarefa
        if tarefa is None:
            self._tarefa_aberta_id = None
            self._alvo_sub = None
            self.pilha.setCurrentIndex(0)
            return
        if tarefa.id != self._tarefa_aberta_id:
            self._alvo_sub = None
        self._tarefa_aberta_id = tarefa.id
        self._carregando = True
        self.pilha.setCurrentIndex(1)
        self.titulo.setText(tarefa.titulo)
        self.titulo.setCursorPosition(0)
        self.tem_prazo.setChecked(tarefa.prazo is not None)
        d = tarefa.prazo or date.today()
        self.prazo.setDate(QDate(d.year, d.month, d.day))
        self.prazo.setEnabled(tarefa.prazo is not None)
        self.tem_inicio.setChecked(tarefa.inicio is not None)
        di = tarefa.inicio or ((tarefa.prazo - timedelta(days=1)) if tarefa.prazo else date.today())
        self.inicio.setDate(QDate(di.year, di.month, di.day))
        h = tarefa.prazo_hora or time(9, 0)
        self.tem_hora.setChecked(tarefa.prazo_hora is not None)
        self.hora.setTime(QTime(h.hour, h.minute))
        self._preencher_repetir(tarefa.repeticao)
        self.duracao.blockSignals(True)
        if self.duracao.findData(tarefa.duracao_min) < 0:
            self.duracao.addItem(f"{tarefa.duracao_min} min", tarefa.duracao_min)
        self.duracao.setCurrentIndex(max(self.duracao.findData(tarefa.duracao_min), 0))
        self.duracao.blockSignals(False)
        self._preencher_lembrar(tarefa.lembretes)
        self._preencher_constante(tarefa.insistir_min)
        self._atualizar_habilitados()
        self.prioridade.setCurrentIndex(int(tarefa.prioridade))
        self.projeto.clear()
        self.projeto.addItem("Sem projeto", None)
        for p in self.janela.servico.banco.listar_projetos():
            self.projeto.addItem(p.nome, p.id)
        indice = self.projeto.findData(tarefa.projeto_id)
        self.projeto.setCurrentIndex(max(indice, 0))
        self.tipo.setCurrentIndex(max(self.tipo.findData(tarefa.tipo), 0))
        self.secao.blockSignals(True)
        self.secao.clear()
        self.secao.addItem("")
        for nome in self.janela.servico.banco.secoes_da_lista(tarefa.projeto_id):
            self.secao.addItem(nome)
        self.secao.setEditText(tarefa.secao)
        self.secao.blockSignals(False)
        self.tags.setText(" ".join(tarefa.tags))
        self.notas.setPlainText(tarefa.notas)
        self._carregar_subs()
        self._carregar_comentarios()
        self._carregar_anexos()
        foco_s = self.janela.servico.foco.segundos_da_tarefa(tarefa.uuid) if tarefa.uuid else 0
        self.rot_foco.setText(f"Tempo de foco nesta tarefa: {formatar_duracao(foco_s)}" if foco_s else "")
        self.rot_foco.setVisible(bool(foco_s))
        self.btn_apagar.setText("Restaurar da lixeira" if tarefa.apagada_em else "Mover para a lixeira")
        self.btn_fixar.setText("Desafixar" if tarefa.fixada else "Fixar")
        self.btn_descartar.setText("Reabrir" if tarefa.descartada else "Não será feito")
        self._carregando = False

    def _carregar_subs(self):
        while self.subs_caixa.count():
            w = self.subs_caixa.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        t = self.tarefa
        servico = self.janela.servico
        diretas = servico.subtarefas(t.id) if t is not None and t.id else []
        feitas = sum(1 for x in diretas if x.concluida)
        self.rot_subs.setText("SUBTAREFAS" + (f"   {feitas}/{len(diretas)}" if diretas else ""))
        arvore = servico.arvore(t.id) if t is not None and t.id else []
        ids = {t.id} | {sub.id for sub, _ in arvore} if t is not None else set()
        if self._alvo_sub is not None and self._alvo_sub not in ids:
            self._alvo_sub = None
        for sub, nivel in arvore:
            linha = QWidget()
            h = QHBoxLayout(linha)
            h.setContentsMargins(18 * (nivel - 1), 0, 0, 0)
            cb = QCheckBox(sub.titulo)
            cb.setChecked(sub.concluida)
            if sub.concluida:
                f = cb.font()
                f.setStrikeOut(True)
                cb.setFont(f)
                cb.setStyleSheet(f"color: {tema.atual.apagado};")
            cb.toggled.connect(lambda _=False, i=sub.id: self._alternar_sub(i))
            h.addWidget(cb, 1)
            if nivel + 1 < MAX_NIVEIS:
                mais = QPushButton("+")
                mais.setObjectName("btnIcone")
                mais.setFixedSize(24, 24)
                mais.setToolTip("Adicionar uma subtarefa dentro desta")
                mais.setCursor(Qt.PointingHandCursor)
                mais.clicked.connect(lambda _=False, i=sub.id, n=sub.titulo: self._escolher_alvo(i, n))
                h.addWidget(mais)
            x = QPushButton("×")
            x.setObjectName("btnIcone")
            x.setFixedSize(24, 24)
            x.setToolTip("Apagar subtarefa")
            x.setCursor(Qt.PointingHandCursor)
            x.clicked.connect(lambda _=False, i=sub.id: self._apagar_sub(i))
            h.addWidget(x)
            self.subs_caixa.addWidget(linha)
        self._atualizar_placeholder_sub()

    def _atualizar_placeholder_sub(self):
        if self._alvo_sub is None or self.tarefa is None:
            self.nova_sub.setPlaceholderText("+  Adicionar subtarefa e apertar Enter")
            return
        alvo = self.janela.servico.banco.obter_tarefa(self._alvo_sub)
        nome = alvo.titulo if alvo else ""
        self.nova_sub.setPlaceholderText(f"+  Dentro de “{nome}” (Esc para voltar ao nível de cima)")

    def _escolher_alvo(self, sub_id: int, _nome: str):
        self._alvo_sub = sub_id
        self._atualizar_placeholder_sub()
        self.nova_sub.setFocus()

    def _alternar_sub(self, sub_id: int):
        self.janela.servico.alternar_conclusao(sub_id)
        self.janela.atualizar(manter_selecao=True)

    def _apagar_sub(self, sub_id: int):
        self.janela.servico.apagar(sub_id)
        self.janela.atualizar(manter_selecao=True)

    def _adicionar_sub(self):
        if self.tarefa is None or not self.nova_sub.text().strip():
            return
        pai = self._alvo_sub or self.tarefa.id
        try:
            self.janela.servico.adicionar_subtarefa(pai, self.nova_sub.text())
        except ValueError:
            return                      # nível máximo atingido
        self.nova_sub.clear()
        self.janela.atualizar(manter_selecao=True)
        self.nova_sub.setFocus()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and self._alvo_sub is not None:
            self._alvo_sub = None
            self._atualizar_placeholder_sub()
            return
        super().keyPressEvent(e)

    def _preencher_repetir(self, regra: str | None):
        self.repetir.clear()
        for nome, valor in recorrencia.PRESETS:
            self.repetir.addItem(nome, valor)
        if regra and self.repetir.findData(regra) < 0:  # regra personalizada: mantém como está
            self.repetir.addItem(recorrencia.descrever(regra), regra)
        self.repetir.addItem("Personalizar...", PERSONALIZAR)
        self.repetir.blockSignals(True)
        self.repetir.setCurrentIndex(max(self.repetir.findData(regra), 0))
        self.repetir.blockSignals(False)
        self._regra_atual = regra

    def _ao_trocar_repetir(self, *_):
        if self._carregando or self.tarefa is None:
            return
        if self.repetir.currentData() == PERSONALIZAR:
            dlg = DialogoRepeticao(self, self._regra_atual)
            if dlg.exec() == QDialog.Accepted:
                self._carregando = True
                self._preencher_repetir(dlg.resultado() or None)
                self._carregando = False
            else:
                self._carregando = True
                self._preencher_repetir(self._regra_atual)
                self._carregando = False
        self._salvar()

    def _preencher_lembrar(self, minutos: list[int]):
        self.lembrar.clear()
        for nome, valor in lembretes_core.ANTECEDENCIAS:
            self.lembrar.addItem(nome, [] if valor is None else [valor])
        atual = list(minutos)
        if self.lembrar.findData(atual) < 0:  # vários lembretes ou valor fora da lista
            texto = ", ".join(lembretes_core.descrever(m) for m in atual)
            self.lembrar.addItem(texto, atual)
        self.lembrar.setCurrentIndex(max(self.lembrar.findData(atual), 0))

    def _preencher_constante(self, minutos: int):
        self.constante.blockSignals(True)
        if self.constante.findData(minutos) < 0:       # valor vindo de outro aparelho
            self.constante.addItem(f"A cada {minutos} minutos", minutos)
        self.constante.setCurrentIndex(max(self.constante.findData(minutos), 0))
        self.constante.blockSignals(False)

    def _atualizar_habilitados(self):
        tem = self.tem_prazo.isChecked()
        self.constante.setEnabled(tem and bool(self.lembrar.currentData()))
        self.prazo.setEnabled(tem)
        self.tem_hora.setEnabled(tem)
        self.hora.setEnabled(tem and self.tem_hora.isChecked())
        self.duracao.setEnabled(tem and self.tem_hora.isChecked())
        self.tem_inicio.setEnabled(tem)
        self.inicio.setEnabled(tem and self.tem_inicio.isChecked())
        self.repetir.setEnabled(tem)
        self.lembrar.setEnabled(tem)

    def _salvar(self, *_):
        if self._carregando or self.tarefa is None:
            return
        t = self.tarefa
        t.titulo = self.titulo.text().strip() or t.titulo
        self._atualizar_habilitados()
        qd = self.prazo.date()
        t.prazo = date(qd.year(), qd.month(), qd.day()) if self.tem_prazo.isChecked() else None
        qi = self.inicio.date()
        t.inicio = (date(qi.year(), qi.month(), qi.day())
                    if t.prazo is not None and self.tem_inicio.isChecked() else None)
        if t.prazo is not None and self.tem_hora.isChecked():
            qt = self.hora.time()
            t.prazo_hora = time(qt.hour(), qt.minute())
        else:
            t.prazo_hora = None
        if t.prazo_hora is not None:
            t.duracao_min = int(self.duracao.currentData() or 0)
        regra = self.repetir.currentData()
        t.repeticao = None if regra == PERSONALIZAR else regra
        t.lembretes = list(self.lembrar.currentData() or [])
        t.insistir_min = int(self.constante.currentData() or 0) if t.lembretes else 0
        t.prioridade = Prioridade(self.prioridade.currentData())
        t.projeto_id = self.projeto.currentData()
        t.tags = [x.lstrip("#").lower() for x in self.tags.text().split() if x.strip("#")]
        t.notas = self.notas.toPlainText()
        t.tipo = self.tipo.currentData() or "tarefa"
        t.secao = self.secao.currentText().strip()
        self.janela.servico.salvar(t)
        self.janela.atualizar(manter_selecao=True)

    # ---- comentários ----
    def _limpar(self, caixa: QVBoxLayout):
        while caixa.count():
            w = caixa.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _carregar_comentarios(self):
        self._limpar(self.coment_caixa)
        t = self.tarefa
        itens = self.janela.servico.comentarios.listar(t.id) if t is not None and t.id else []
        self.rot_coment.setText("COMENTÁRIOS" + (f"   {len(itens)}" if itens else ""))
        pal = tema.atual
        from dateutil import tz
        for c in itens:
            quadro = QWidget()
            h = QHBoxLayout(quadro)
            h.setContentsMargins(0, 0, 0, 0)
            col = QVBoxLayout()
            col.setSpacing(0)
            hora = c.criado_em.replace(tzinfo=c.criado_em.tzinfo or tz.tzutc()).astimezone(tz.tzlocal())
            quando = QLabel(f"{hora:%d/%m/%Y %H:%M}")
            quando.setStyleSheet(f"font-size: 10px; color: {pal.apagado};")
            texto = QLabel(c.texto)
            texto.setWordWrap(True)
            texto.setTextInteractionFlags(Qt.TextSelectableByMouse)
            col.addWidget(quando)
            col.addWidget(texto)
            h.addLayout(col, 1)
            x = QPushButton("×")
            x.setObjectName("btnIcone")
            x.setFixedSize(24, 24)
            x.setToolTip("Apagar comentário")
            x.setCursor(Qt.PointingHandCursor)
            x.clicked.connect(lambda _=False, u=c.uuid: self._apagar_comentario(u))
            h.addWidget(x, 0, Qt.AlignTop)
            self.coment_caixa.addWidget(quadro)

    def _adicionar_comentario(self):
        if self.tarefa is None or not self.novo_coment.text().strip():
            return
        self.janela.servico.comentarios.adicionar(self.tarefa.id, self.novo_coment.text())
        self.novo_coment.clear()
        self._carregar_comentarios()

    def _apagar_comentario(self, uuid: str):
        self.janela.servico.comentarios.apagar(uuid)
        self._carregar_comentarios()

    # ---- anexos ----
    def _carregar_anexos(self):
        self._limpar(self.anexos_caixa)
        t = self.tarefa
        habilitado = self.janela.servico.pasta_dados is not None
        for w in (self.rot_anexos, self.btn_anexar):
            w.setVisible(habilitado)
        if not habilitado or t is None or not t.id:
            return
        itens = self.janela.servico.anexos.listar(t.id)
        self.rot_anexos.setText("ANEXOS" + (f"   {len(itens)}" if itens else "") + "  (só neste computador)")
        for a in itens:
            linha = QWidget()
            h = QHBoxLayout(linha)
            h.setContentsMargins(0, 0, 0, 0)
            abrir = QPushButton(a.nome)
            abrir.setObjectName("btnBarra")
            abrir.setStyleSheet("QPushButton { text-align: left; padding: 4px 0; border: none; "
                                f"color: {tema.atual.destaque}; background: transparent; }}")
            abrir.setCursor(Qt.PointingHandCursor)
            abrir.setToolTip(f"Abrir ({a.tamanho // 1024} KB)")
            abrir.clicked.connect(lambda _=False, c=a.caminho: QDesktopServices.openUrl(QUrl.fromLocalFile(c)))
            h.addWidget(abrir, 1)
            x = QPushButton("×")
            x.setObjectName("btnIcone")
            x.setFixedSize(24, 24)
            x.setToolTip("Remover anexo")
            x.setCursor(Qt.PointingHandCursor)
            x.clicked.connect(lambda _=False, i=a.id: self._remover_anexo(i))
            h.addWidget(x)
            self.anexos_caixa.addWidget(linha)

    def anexar(self, caminho: str | None = None):
        if self.tarefa is None:
            return
        if caminho is None:
            caminho, _ = QFileDialog.getOpenFileName(self, "Escolha o arquivo para anexar")
            if not caminho:
                return
        try:
            self.janela.servico.anexos.adicionar(self.tarefa.id, caminho)
        except (ValueError, RuntimeError) as e:
            QMessageBox.warning(self, "Anexo", str(e))
            return
        self._carregar_anexos()

    def _remover_anexo(self, anexo_id: int):
        self.janela.servico.anexos.remover(anexo_id)
        self._carregar_anexos()

    def _apagar(self):
        if self.tarefa is None:
            return
        if self.tarefa.apagada_em:
            self.janela.servico.restaurar(self.tarefa.id)
        else:
            self.janela.servico.apagar(self.tarefa.id)
        self.janela.atualizar()


def icone_do_app() -> QIcon:
    """Ícone do app: quadrado azul com um check, desenhado em código."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(tema.atual.destaque))
    p.drawRoundedRect(6, 6, 52, 52, 14, 14)
    p.setPen(QPen(QColor("#ffffff"), 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawLine(20, 33, 28, 41)
    p.drawLine(28, 41, 44, 24)
    p.end()
    return QIcon(pm)


class JanelaPrincipal(QMainWindow):
    def __init__(self, servico: Servico, notificador=None, intervalo_lembretes_ms: int = 20_000,
                 sincronizador=None, ao_configurar_sync=None, sync_em_thread: bool = True,
                 intervalo_sync_ms: int = 60_000, intervalo_google_ms: int = 300_000,
                 google_em_thread: bool = True, prefs: dict | None = None, ao_salvar_prefs=None):
        """`notificador(titulo, texto)` mostra o aviso; por padrão usa a bandeja do sistema.

        `sincronizador` é um norteia.sync.Sincronizador (ou None para uso só local);
        `ao_configurar_sync(url, token)` guarda a configuração e devolve o novo sincronizador.
        `prefs` são as preferências (notificações) e `ao_salvar_prefs(prefs)` as grava."""
        super().__init__()
        self.servico = servico
        self.prefs = prefs if prefs is not None else {}
        self._ao_salvar_prefs = ao_salvar_prefs
        self._notificador_proprio = notificador is not None
        self._saindo = False
        self._autostart = autostart                      # trocável nos testes
        self._bandeja_disponivel = QSystemTrayIcon.isSystemTrayAvailable   # trocável nos testes
        self.avisos = GerenteAvisos(self._concluir_pelo_aviso, self._adiar_pelo_aviso)
        self.sincronizador = sincronizador
        self._ao_configurar_sync = ao_configurar_sync
        self._sync_em_thread = sync_em_thread
        self._sincronizando = False
        self._sinais_sync = _SinaisSync()
        self._sinais_ia = _SinaisIA()
        self._ia_em_thread = True
        self._ia_quebrar = ia.quebrar                    # trocável nos testes
        self._ia_ocupada = False
        self._bandeja: QSystemTrayIcon | None = None
        self.notificador = notificador or self._notificar_pela_bandeja
        self.lista_atual: str | int = HOJE
        self.ordem_atual = "data"
        self.agrupar_atual = "nenhum"
        self.pagina_atual = "tarefas"
        self.visao_atual = "lista"
        self._barra_visivel = True
        self._selecionada: int | None = None
        self._da_tela: list = []
        self.setWindowTitle(NOME)
        self.setMinimumSize(900, 560)        # explícito: sem isso o tamanho mínimo vira a soma das páginas e passa da tela
        self.resize(1360, 820)
        self.setStyleSheet(tema.qss())
        pal = tema.atual

        raiz = QWidget()
        raiz.setObjectName("raiz")
        self.setCentralWidget(raiz)
        horizontal = QHBoxLayout(raiz)
        horizontal.setContentsMargins(0, 0, 0, 0)
        horizontal.setSpacing(0)

        # coluna fina de ícones
        trilho = QWidget()
        trilho.setObjectName("trilho")
        trilho.setAttribute(Qt.WA_StyledBackground, True)
        trilho.setFixedWidth(64)
        lay_t = QVBoxLayout(trilho)
        lay_t.setContentsMargins(10, 18, 10, 12)
        lay_t.setSpacing(6)
        self.btns_pagina: dict[str, QPushButton] = {}
        self.grupo_paginas = QButtonGroup(self)
        self.grupo_paginas.setExclusive(True)
        # avatar no topo (abre o menu da conta/configurações)
        self.btn_avatar = self._botao_avatar(str(self.prefs.get("nome_usuario") or "G"))
        lay_t.addWidget(self.btn_avatar, 0, Qt.AlignHCenter)
        lay_t.addSpacing(6)
        # a busca "em linha" (filtra a lista) continua existindo, mas o botão da barra abre a busca flutuante
        self.btn_busca = self._botao_trilho("busca", "Buscar (Ctrl+K)", ativo=True)
        self.btn_busca.setCheckable(True)
        self.btn_busca.setParent(trilho)
        self.btn_busca.hide()
        self.btn_buscar = self._botao_trilho("busca", "Buscar (Ctrl+K)", ativo=True)
        for chave, icone, dica in PAGINAS:
            b = self._botao_trilho(icone, dica, ativo=True)
            b.setCheckable(True)
            self.grupo_paginas.addButton(b)
            self.btns_pagina[chave] = b
            if chave in SECUNDARIAS:                 # Contagem e Estatísticas ficam no menu "…"
                b.setParent(trilho)
                b.hide()
                continue
            lay_t.addWidget(b)
        lay_t.addWidget(self.btn_buscar)
        self.btn_tarefas = self.btns_pagina["tarefas"]
        self.btn_tarefas.setChecked(True)
        lay_t.addStretch(1)
        self.btn_sync = self._botao_trilho("repetir", "Sincronizar", ativo=True)
        self.btn_sync.setContextMenuPolicy(Qt.CustomContextMenu)
        lay_t.addWidget(self.btn_sync)
        self.btn_config = self._botao_trilho("engrenagem", "Configurações (Ctrl+,)", ativo=True)
        lay_t.addWidget(self.btn_config)
        horizontal.addWidget(trilho)

        # barra lateral
        self.barra_caixa = QWidget()
        self.barra_caixa.setFixedWidth(272)
        self.barra_caixa.setObjectName("barra")
        self.barra_caixa.setAttribute(Qt.WA_StyledBackground, True)
        lay_b = QVBoxLayout(self.barra_caixa)
        lay_b.setContentsMargins(0, 18, 0, 8)
        lay_b.setSpacing(0)
        self.barra = QListWidget()
        self.barra.setMouseTracking(True)
        self.barra.setItemDelegate(DelegadoBarra(self.barra))
        self.barra.setFocusPolicy(Qt.NoFocus)
        self.barra.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay_b.addWidget(self.barra, 1)
        horizontal.addWidget(self.barra_caixa)

        # centro
        centro = QWidget()
        centro.setObjectName("centro")
        centro.setAttribute(Qt.WA_StyledBackground, True)
        lay_c = QVBoxLayout(centro)
        lay_c.setContentsMargins(22, 18, 22, 12)
        lay_c.setSpacing(0)
        cabecalho = QHBoxLayout()
        cabecalho.setSpacing(6)
        self.btn_menu = self._botao_icone("menu", "Mostrar ou esconder a barra lateral")
        cabecalho.addWidget(self.btn_menu)
        self.titulo = QLabel()
        self.titulo.setObjectName("titulo")
        cabecalho.addWidget(self.titulo)
        cabecalho.addStretch(1)
        self.btn_modelos = self._botao_icone("modelo", "Modelos de tarefa")
        cabecalho.addWidget(self.btn_modelos)
        self.btn_visao = self._botao_icone("kanban", "Visualização: lista, Kanban ou linha do tempo")
        cabecalho.addWidget(self.btn_visao)
        self.btn_ordenar = self._botao_icone("ordenar", "Ordenar")
        cabecalho.addWidget(self.btn_ordenar)
        lay_c.addLayout(cabecalho)
        lay_c.addSpacing(14)

        self.busca = QLineEdit()
        self.busca.setObjectName("entrada")
        self.busca.setPlaceholderText("Buscar em título, notas e etiquetas")
        self.busca.setVisible(False)
        lay_c.addWidget(self.busca)

        self.entrada = QLineEdit()
        self.entrada.setObjectName("entrada")
        self.entrada.setPlaceholderText("Adicionar uma tarefa    ex.: Pagar conta amanhã às 9h !2 #casa")
        mais = QLabel(self.entrada)
        mais.setPixmap(icones.pixmap("mais", pal.apagado, 16))
        mais.setGeometry(13, 13, 16, 16)
        mais.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lay_c.addWidget(self.entrada)
        lay_c.addSpacing(6)
        self.tarefas = ListaTarefas(self.alternar)
        self.delegado = DelegadoTarefa(self.tarefas)
        self.tarefas.setItemDelegate(self.delegado)
        lay_c.addWidget(self.tarefas, 1)
        self.vazio = QLabel("Nada por aqui.")
        self.vazio.setAlignment(Qt.AlignCenter)
        self.vazio.setObjectName("mensagemVazia")
        lay_c.addWidget(self.vazio, 1)
        self.kanban = VistaKanban(self)
        self.linha_tempo = VistaLinhaTempo(self)
        for v in (self.kanban, self.linha_tempo):
            v.setVisible(False)
            lay_c.addWidget(v, 1)

        self.pilha_paginas = QStackedWidget()
        self.pilha_paginas.addWidget(centro)
        self.pagina_calendario = PaginaCalendario(self)
        self.pagina_matriz = PaginaMatriz(self)
        self.pagina_foco = PaginaFoco(self)
        self.pagina_habitos = PaginaHabitos(self)
        self.pagina_contagem = PaginaContagem(self)
        self.pagina_estatisticas = PaginaEstatisticas(self)
        self.pagina_ia = PaginaIA(self)
        self.paginas = {"tarefas": centro, "calendario": self.pagina_calendario, "matriz": self.pagina_matriz,
                        "foco": self.pagina_foco, "habitos": self.pagina_habitos,
                        "contagem": self.pagina_contagem, "estatisticas": self.pagina_estatisticas,
                        "ia": self.pagina_ia}
        for chave in ("calendario", "matriz", "foco", "habitos", "contagem", "estatisticas", "ia"):
            self.pilha_paginas.addWidget(self.paginas[chave])
        horizontal.addWidget(self.pilha_paginas, 1)

        # detalhe
        self.detalhe = PainelDetalhe(self)
        horizontal.addWidget(self.detalhe)
        # cartão ampliado na lateral (modo lista): o mesmo cartão do calendário, fixo e com gravação automática
        self.cartao_acoplado: CartaoTarefa | None = None
        self.painel_cartao = QFrame()
        self.painel_cartao.setObjectName("painelCartao")
        self.painel_cartao.setFixedWidth(440)
        lay_pc = QVBoxLayout(self.painel_cartao)
        lay_pc.setContentsMargins(0, 0, 0, 0)
        lay_pc.setSpacing(0)
        self.vazio_cartao = QLabel("Selecione uma tarefa\npara editar")
        self.vazio_cartao.setAlignment(Qt.AlignCenter)
        self.vazio_cartao.setStyleSheet(f"color: {tema.atual.apagado}; font-size: 13px;")
        lay_pc.addWidget(self.vazio_cartao, 1)
        self.painel_cartao.setVisible(False)
        horizontal.addWidget(self.painel_cartao)

        # menu de ordenação
        self.menu_ordem = QMenu(self)
        for chave, nome in ORDENS:
            self.menu_ordem.addAction(nome, lambda c=chave: self.definir_ordem(c))
        self.menu_ordem.addSeparator()
        sub_agrupar = self.menu_ordem.addMenu("Agrupar por")
        for chave, nome in AGRUPAMENTOS:
            sub_agrupar.addAction(nome, lambda c=chave: self.definir_agrupamento(c))
        self.btn_ordenar.clicked.connect(
            lambda: self.menu_ordem.exec(self.btn_ordenar.mapToGlobal(self.btn_ordenar.rect().bottomLeft())))
        self.btn_visao.clicked.connect(self._menu_visao)
        self.btn_modelos.clicked.connect(self._menu_modelos)
        for chave, b in self.btns_pagina.items():
            b.clicked.connect(lambda _=False, c=chave: self.mostrar_pagina(c))

        # ligações
        self.barra.currentItemChanged.connect(self._ao_trocar_lista)
        self.tarefas.currentItemChanged.connect(self._ao_selecionar_tarefa)
        self.tarefas.clicou_tarefa.connect(self.abrir_cartao_da_tarefa)
        self.tarefas.itemActivated.connect(self._ativou_tarefa)
        self.entrada.returnPressed.connect(self._adicionar)
        self.busca.textChanged.connect(lambda _: self.atualizar())
        self.btn_busca.toggled.connect(self._alternar_busca)
        self.painel_busca = PainelBusca(self)
        self.btn_buscar.clicked.connect(lambda: self.abrir_busca())
        self.btn_avatar.clicked.connect(self._menu_config)
        self.barra.itemClicked.connect(self._clicou_na_barra)
        self.barra.setContextMenuPolicy(Qt.CustomContextMenu)
        self.barra.customContextMenuRequested.connect(self._menu_da_barra)
        self.tarefas.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tarefas.customContextMenuRequested.connect(self._menu_da_tarefa)
        self.btn_config.clicked.connect(self._menu_config)
        self.tarefas.model().rowsMoved.connect(lambda *_: QTimer.singleShot(0, self.aplicar_ordem_da_lista))
        self.btn_menu.clicked.connect(self.alternar_barra)
        self.btn_sync.clicked.connect(self.sincronizar_agora)
        self.btn_sync.customContextMenuRequested.connect(self._menu_sync)
        self._sinais_sync.pronto.connect(self._fim_sync)
        self._sinais_ia.pronto.connect(self._fim_ia)
        self.janela_rapida = JanelaRapida(self.servico, self)
        self.janela_rapida.criada.connect(lambda t: self.atualizar(manter_selecao=True))
        QShortcut(QKeySequence("F5"), self, activated=self.sincronizar_agora)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.entrada.setFocus)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.abrir_busca)
        QShortcut(QKeySequence("Delete"), self.tarefas, activated=self._apagar_selecionada)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.abrir_busca)
        QShortcut(QKeySequence("Ctrl+B"), self, activated=self.alternar_barra)
        for i, (chave, _i, _d) in enumerate(PAGINAS, start=1):
            QShortcut(QKeySequence(f"Ctrl+{i}"), self, activated=lambda c=chave: self.mostrar_pagina(c))
        QShortcut(QKeySequence("Ctrl+D"), self, activated=lambda: self._com_selecionada(self.duplicar_tarefa))
        QShortcut(QKeySequence("Ctrl+P"), self, activated=lambda: self._com_selecionada(self.fixar_tarefa))
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=lambda: self._com_selecionada(self.alternar))
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self.abrir_configuracoes)
        QShortcut(QKeySequence("F1"), self, activated=self.mostrar_atalhos)

        self.setWindowIcon(icone_do_app())
        self.atualizar()

        # lembretes: confere de tempos em tempos e ao abrir
        self.relogio = QTimer(self)
        self.relogio.timeout.connect(self.verificar_lembretes)
        self.relogio.start(intervalo_lembretes_ms)
        QTimer.singleShot(0, self.verificar_lembretes)

        # sincronização automática (só se estiver configurada)
        self._pedido_sync = None
        self.relogio_sync = QTimer(self)
        self.relogio_sync.timeout.connect(self._sync_automatica)
        self.relogio_sync.start(intervalo_sync_ms)
        self._atualizar_icone_sync("ocioso")
        QTimer.singleShot(1500, self._sync_automatica)

        # Google Calendar (só faz algo depois que a conta é conectada)
        self.gerente_google = GerenteGoogle(self.servico, em_thread=google_em_thread)
        self.gerente_google.terminou.connect(self._google_terminou)
        self.relogio_google = QTimer(self)
        self.relogio_google.timeout.connect(self.gerente_google.sincronizar)
        self.relogio_google.start(intervalo_google_ms)
        QTimer.singleShot(4000, self.gerente_google.sincronizar)

    # ---- sincronização ----
    def _atualizar_icone_sync(self, estado: str, detalhe: str = ""):
        pal = tema.atual
        cor = {"ocioso": pal.texto, "ok": pal.texto, "erro": pal.vermelho, "ocupado": pal.destaque}[estado]
        self.btn_sync.setIcon(icones.icone("repetir", cor, 24))
        if self.sincronizador is None:
            dica = "Sincronização desligada. Clique para configurar."
        else:
            dica = detalhe or "Sincronizar agora (F5). Botão direito: configurar."
        self.btn_sync.setToolTip(dica)

    def _menu_sync(self, pos):
        menu = QMenu(self)
        menu.addAction("Sincronizar agora", self.sincronizar_agora)
        menu.addAction("Configurar sincronização...", self.configurar_sincronizacao)
        menu.exec(self.btn_sync.mapToGlobal(pos))

    def configurar_sincronizacao(self):
        url, token = ("", "")
        if self._ao_configurar_sync is None:
            return
        atual = getattr(self._ao_configurar_sync, "atual", None)
        if callable(atual):
            url, token = atual()
        dlg = DialogoSincronizacao(self, url, token)
        if dlg.exec() == QDialog.Accepted:
            self.sincronizador = self._ao_configurar_sync(*dlg.resultado())
            self._atualizar_icone_sync("ocioso")
            if self.sincronizador is not None:
                self.sincronizar_agora()

    def _sync_automatica(self):
        if self.sincronizador is not None:
            self.sincronizar_agora()

    def sincronizar_agora(self):
        if self.sincronizador is None:
            self.configurar_sincronizacao()
            return
        if self._sincronizando:
            return
        self._sincronizando = True
        self._atualizar_icone_sync("ocupado", "Sincronizando...")
        pedido = self.sincronizador.preparar()
        if self._sync_em_thread:
            sinais = self._sinais_sync
            self._pedido_sync = pedido
            QThreadPool.globalInstance().start(_EnvioSync(lambda: self.sincronizador.enviar(pedido), sinais))
        else:
            try:
                self._fim_sync_com(pedido, self.sincronizador.enviar(pedido), None)
            except Exception as e:  # noqa: BLE001
                self._fim_sync_com(pedido, None, e)

    def _fim_sync(self, resposta, erro):
        self._fim_sync_com(self._pedido_sync, resposta, erro)

    def _fim_sync_com(self, pedido, resposta, erro):
        self._sincronizando = False
        if erro is not None:
            self._atualizar_icone_sync("erro", f"Falha ao sincronizar: {erro}")
            return
        if self.detalhe.tarefa is not None:
            self.detalhe._salvar()        # não perde o que está sendo digitado
        resumo = self.sincronizador.aplicar(pedido, resposta)
        self._atualizar_icone_sync("ok", f"Sincronizado às {datetime.now():%H:%M}: {resumo}")
        if resumo.recebidos:
            self.atualizar(manter_selecao=True)
            self.verificar_lembretes()

    # ---- peças ----
    @staticmethod
    def _botao_trilho(nome: str, dica: str, ativo: bool) -> QPushButton:
        pal = tema.atual
        b = QPushButton()
        b.setObjectName("btnTrilho")
        b.setFixedSize(44, 44)
        b.setIcon(icones.icone(nome, pal.texto if ativo else "#4d4d4d", 24))
        b.setIconSize(QSize(24, 24))
        b.setToolTip(dica)
        b.setEnabled(ativo)
        b.setCursor(Qt.PointingHandCursor if ativo else Qt.ArrowCursor)
        return b

    @staticmethod
    def _botao_avatar(nome: str) -> QPushButton:
        """Bolinha com a inicial do nome."""
        pal = tema.atual
        b = QPushButton()
        b.setObjectName("btnAvatar")
        b.setFixedSize(36, 36)
        pm = QPixmap(72, 72)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#4d4d4d"))
        p.drawEllipse(0, 0, 72, 72)
        p.setPen(QColor(pal.texto))
        f = p.font()
        f.setPixelSize(34)
        f.setBold(True)
        p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignCenter, (nome.strip()[:1] or "G").upper())
        p.end()
        pm.setDevicePixelRatio(2)
        b.setIcon(QIcon(pm))
        b.setIconSize(QSize(36, 36))
        b.setStyleSheet("QPushButton#btnAvatar { background: transparent; border: none; padding: 0; }")
        b.setToolTip("Conta e configurações")
        b.setCursor(Qt.PointingHandCursor)
        return b

    def abrir_busca(self, texto: str = ""):
        """Abre a busca flutuante (Ctrl+K)."""
        self.painel_busca.abrir(texto)

    @staticmethod
    def _botao_icone(nome: str, dica: str) -> QPushButton:
        b = QPushButton()
        b.setObjectName("btnIcone")
        b.setFixedSize(34, 34)
        b.setIcon(icones.icone(nome, tema.atual.apagado, 20))
        b.setIconSize(QSize(20, 20))
        b.setToolTip(dica)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _alternar_busca(self, ligada: bool):
        if ligada and self.pagina_atual != "tarefas":
            self.mostrar_pagina("tarefas")
        self.busca.setVisible(ligada)
        if ligada:
            self.busca.setFocus()
        else:
            self.busca.clear()
        self.atualizar()

    def definir_ordem(self, chave: str):
        self.ordem_atual = chave
        self.atualizar(manter_selecao=True)

    # ---- lembretes ----
    def _garantir_bandeja(self) -> QSystemTrayIcon | None:
        """Ícone na bandeja do sistema (perto do relógio), com menu. None se o sistema não tem bandeja."""
        if self._bandeja is None and self._bandeja_disponivel():
            self._bandeja = QSystemTrayIcon(icone_do_app(), self)
            self._bandeja.setToolTip(NOME)
            menu = QMenu(self)
            menu.addAction(f"Abrir {NOME}", self.restaurar)
            menu.addAction("Nova tarefa rápida (Ctrl+Alt+N)", self.abrir_tarefa_rapida)
            menu.addAction("Nova tarefa", lambda: (self.restaurar(), self.entrada.setFocus()))
            menu.addAction("Sincronizar agora", self.sincronizar_agora)
            menu.addSeparator()
            menu.addAction("Sair", self.sair)
            self._menu_bandeja = menu
            self._bandeja.setContextMenu(menu)
            self._bandeja.activated.connect(
                lambda motivo: self.restaurar() if motivo == QSystemTrayIcon.Trigger else None)
            self._bandeja.show()
        return self._bandeja

    def _notificar_pela_bandeja(self, titulo: str, texto: str):
        bandeja = self._garantir_bandeja()
        if bandeja is not None:
            bandeja.showMessage(titulo, texto, QSystemTrayIcon.Information, 10_000)

    def restaurar(self):
        """Traz a janela de volta (depois de ter ficado só na bandeja)."""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def sair(self):
        """Encerra de verdade (o X da janela só esconde, se a opção da bandeja estiver ligada)."""
        self._saindo = True
        if self._bandeja is not None:
            self._bandeja.hide()
        self.close()
        QCoreApplication.quit()

    def iniciar_na_bandeja(self):
        """Usado ao abrir com o Windows: fica só o ícone perto do relógio."""
        self._garantir_bandeja()
        self.hide()

    def closeEvent(self, e):
        if self.prefs.get("fechar_para_bandeja", False) and not self._saindo and self._garantir_bandeja():
            e.ignore()
            self.hide()
            if not self.prefs.get("aviso_bandeja_visto", False):
                self.prefs["aviso_bandeja_visto"] = True
                if self._ao_salvar_prefs is not None:
                    self._ao_salvar_prefs(self.prefs)
                self._bandeja.showMessage(
                    f"O {NOME} continua aberto", "Ele fica aqui perto do relógio para avisar dos seus "
                    "lembretes. Clique com o botão direito no ícone para sair.", QSystemTrayIcon.Information, 8000)
            return
        self.pagina_foco.encerrar()
        super().closeEvent(e)

    def verificar_lembretes(self, agora: datetime | None = None) -> list:
        """Dispara os lembretes vencidos (uma vez cada) e devolve quais foram."""
        avisos = self.servico.lembretes_vencidos(agora)
        for lembrete in avisos:
            self._mostrar_lembrete(lembrete)
            self.servico.marcar_avisado(lembrete)
        for h in self.servico.habitos.lembretes_vencidos(agora):
            self.notificador(f"Hábito: {h.nome}", "Ainda dá tempo de marcar o de hoje.")
            self.servico.habitos.marcar_avisado(h, (agora or datetime.now()).date())
        if self.prefs.get("resumo_diario", False):
            hora = datetime.strptime(str(self.prefs.get("resumo_hora", "08:00")), "%H:%M").time()
            resumo = self.servico.resumo_diario(agora, hora)
            if resumo is not None:
                self.notificador("Resumo do dia", resumo.texto)
        return avisos

    def _mostrar_lembrete(self, lembrete):
        """Janelinha com Adiar e Concluir; se desligada (ou se alguém passou um notificador), aviso simples."""
        if self._notificador_proprio or not self.prefs.get("aviso_na_tela", True):
            self.notificador(lembrete.titulo, lembrete.texto)
        else:
            self.avisos.mostrar(lembrete.tarefa.id, lembrete.titulo, lembrete.texto)

    def _concluir_pelo_aviso(self, tarefa_id: int):
        self.servico.alternar_conclusao(tarefa_id)
        self.atualizar(manter_selecao=True)

    def _adiar_pelo_aviso(self, tarefa_id: int, minutos):
        self.adiar_tarefa(tarefa_id, minutos)

    def adiar_tarefa(self, tarefa_id: int, minutos: int | None):
        """Soneca. `minutos=None` adia para amanhã de manhã."""
        if minutos is None:
            self.servico.adiar_para_amanha(tarefa_id)
        else:
            self.servico.adiar(tarefa_id, minutos)

    def abrir_configuracoes(self):
        dlg = DialogoConfiguracoes(self, self.prefs)
        if dlg.exec() == QDialog.Accepted:
            self.aplicar_preferencias(dlg.resultado())

    def aplicar_preferencias(self, novas: dict):
        self.prefs.update(novas)
        if "iniciar_com_windows" in novas:
            self._autostart.definir(bool(novas["iniciar_com_windows"]))
        if self._ao_salvar_prefs is not None:
            self._ao_salvar_prefs(self.prefs)

    def mostrar_atalhos(self):
        texto = "\n".join(f"{tecla:<18} {descricao}" for tecla, descricao in ATALHOS)
        QMessageBox.information(self, "Atalhos de teclado", texto)

    # ---- ações ----
    def _adicionar(self):
        texto = self.entrada.text().strip()
        if not texto:
            return
        projeto = self.lista_atual if isinstance(self.lista_atual, int) else None
        t = self.servico.adicionar_rapido(texto, projeto_id=projeto)
        mudou = False
        if self.lista_atual == HOJE and t.prazo is None:
            t.prazo = date.today()
            mudou = True
        if isinstance(self.lista_atual, str) and self.lista_atual.startswith(PREFIXO_TAG):
            nome = self.lista_atual[len(PREFIXO_TAG):]
            if nome not in t.tags:
                t.tags.append(nome)
                mudou = True
        if mudou:
            self.servico.salvar(t)
        self.entrada.clear()
        if self.lista_atual in (CONCLUIDAS, LIXEIRA, BUSCA):
            self.lista_atual = HOJE if t.prazo else CAIXA
        self.atualizar(selecionar_id=t.id)

    def alternar(self, tarefa_id: int):
        self.servico.alternar_conclusao(tarefa_id)
        self.atualizar()

    def _com_selecionada(self, acao):
        if self._selecionada is not None:
            acao(self._selecionada)

    def duplicar_tarefa(self, tarefa_id: int):
        copia = self.servico.duplicar(tarefa_id)
        self.atualizar(selecionar_id=copia.id)

    def fixar_tarefa(self, tarefa_id: int):
        self.servico.alternar_fixada(tarefa_id)
        self.atualizar(selecionar_id=tarefa_id)

    def descartar_tarefa(self, tarefa_id: int):
        self.servico.alternar_descarte(tarefa_id)
        self.atualizar()

    def mover_tarefa(self, tarefa_id: int, projeto_id: int | None):
        t = self.servico.banco.obter_tarefa(tarefa_id)
        t.projeto_id = projeto_id
        self.servico.salvar(t)
        for sub in self.servico.descendentes(tarefa_id):
            sub.projeto_id = projeto_id
            self.servico.salvar(sub)
        self.atualizar(manter_selecao=True)

    def definir_prioridade_tarefa(self, tarefa_id: int, prioridade: int):
        t = self.servico.banco.obter_tarefa(tarefa_id)
        t.prioridade = Prioridade(prioridade)
        self.servico.salvar(t)
        self.atualizar(manter_selecao=True)

    def _menu_da_tarefa(self, pos):
        item = self.tarefas.itemAt(pos)
        if item is None or item.data(PAPEL_TAREFA) is None:
            return
        self.tarefas.setCurrentItem(item)
        self.menu_da_tarefa_id(item.data(PAPEL_TAREFA).id, self.tarefas.mapToGlobal(pos))

    def menu_da_tarefa_id(self, tarefa_id: int | None, pos_global, externo=None, executar: bool = True):
        """Menu de contexto de uma tarefa, usado pela lista, pelo Kanban, pelo calendário e pela matriz.

        `externo` é a ocorrência do calendário (para eventos de outros calendários, sem tarefa)."""
        menu = QMenu(self)
        if tarefa_id is None:
            if externo is not None:
                menu.addAction("Evento de calendário externo (somente leitura)").setEnabled(False)
                menu.addAction("Criar tarefa a partir deste evento", lambda: self.tarefa_de_evento(externo))
                if getattr(externo, "link", ""):
                    menu.addAction("Abrir no Google Calendar",
                                   lambda: QDesktopServices.openUrl(QUrl(externo.link)))
            if executar and not menu.isEmpty():
                menu.exec(pos_global)
            return menu
        t = self.servico.banco.obter_tarefa(tarefa_id)
        if t is None:
            return menu
        if t.apagada_em:
            menu.addAction("Restaurar da lixeira", lambda: (self.servico.restaurar(t.id), self.atualizar()))
            if executar:
                menu.exec(pos_global)
            return menu
        menu.addAction("Reabrir" if t.finalizada else "Concluir", lambda: self.alternar(t.id))
        menu.addAction("Desafixar" if t.fixada else "Fixar no topo", lambda: self.fixar_tarefa(t.id))
        menu.addAction("Duplicar", lambda: self.duplicar_tarefa(t.id))
        menu.addAction("Iniciar foco", lambda: self.iniciar_foco_na_tarefa(t.id))
        menu.addSeparator()
        if not t.finalizada:
            adiar = menu.addMenu("Lembrar de novo em...")
            for nome, minutos in OPCOES_SONECA:
                adiar.addAction(nome, lambda m=minutos: self.adiar_tarefa(t.id, m))
        mover = menu.addMenu("Mover para")
        mover.addAction("Caixa de Entrada", lambda: self.mover_tarefa(t.id, None))
        for proj in self.servico.banco.listar_projetos():
            mover.addAction(proj.nome, lambda i=proj.id: self.mover_tarefa(t.id, i))
        prio = menu.addMenu("Prioridade")
        for valor in (3, 2, 1, 0):
            prio.addAction(tema.NOME_PRIORIDADE[valor], lambda v=valor: self.definir_prioridade_tarefa(t.id, v))
        menu.addAction("Reabrir (não será feito)" if t.descartada else "Não será feito",
                       lambda: self.descartar_tarefa(t.id))
        menu.addAction("Salvar como modelo...", lambda: self.salvar_modelo(t.id))
        menu.addSeparator()
        menu.addAction("Mover para a lixeira", lambda: (self.servico.apagar(t.id), self.atualizar()))
        if executar:
            menu.exec(pos_global)
        return menu

    def tarefa_de_evento(self, o):
        """Cria uma tarefa de verdade a partir de um evento de calendário externo."""
        t = self.servico.adicionar_rapido(o.titulo)
        t.prazo, t.prazo_hora = o.inicio, o.hora
        if o.varios_dias:
            t.inicio, t.prazo = o.inicio, o.fim
        if o.hora is not None:
            t.duracao_min = o.duracao_min
            t.lembretes = [0]
        self.servico.salvar(t)
        self.atualizar(selecionar_id=t.id)

    def _apagar_selecionada(self):
        item = self.tarefas.currentItem()
        if item and item.data(PAPEL_TAREFA) is not None:
            self.servico.apagar(item.data(PAPEL_TAREFA).id)
            self.atualizar()

    def _clicou_na_barra(self, item):
        """O "+" que aparece ao lado de Listas, Etiquetas e Filtros."""
        chave = str(item.data(PAPEL_CHAVE) or "")
        if item.data(PAPEL_TIPO) != "cabecalho" or not chave.startswith("novo:"):
            return
        pos = self.barra.viewport().mapFromGlobal(QCursor.pos())
        if not DelegadoBarra.rect_mais(self.barra.visualItemRect(item)).contains(pos):
            return
        {"novo:lista": self._novo_projeto, "novo:etiqueta": self._nova_etiqueta,
         "novo:filtro": self._novo_filtro}[chave]()

    def _pastas_existentes(self) -> list[str]:
        return sorted({p.pasta for p in self.servico.banco.listar_projetos() if p.pasta}, key=str.lower)

    def _novo_projeto(self):
        dlg = DialogoLista(self, CORES_LISTAS, self._pastas_existentes())
        if dlg.exec() == QDialog.Accepted:
            d = dlg.resultado()
            cor = d["cor"] if d["cor"] != SEM_COR else SEM_COR
            p = self.servico.criar_projeto(d["nome"], cor, emoji=d["emoji"], visao=d["visao"], pasta=d["pasta"],
                                           tipo=d["tipo"], inteligente=d["inteligente"])
            self.lista_atual = p.id
            self.atualizar()

    def editar_projeto(self, projeto_id: int):
        p = self.servico.banco.obter_projeto(projeto_id)
        if p is None:
            return
        dlg = DialogoLista(self, CORES_LISTAS, self._pastas_existentes(), p)
        if dlg.exec() == QDialog.Accepted:
            self.servico.atualizar_projeto(projeto_id, **dlg.resultado())
            self.atualizar(manter_selecao=True)

    def _nova_etiqueta(self):
        nome, ok = QInputDialog.getText(self, "Nova etiqueta", "Nome da etiqueta:")
        if ok and nome.strip():
            try:
                self.servico.criar_tag(nome.strip())
            except (ValueError, AttributeError):
                return
            self.atualizar(manter_selecao=True)

    def _novo_filtro(self):
        dlg = DialogoFiltro(self, self.servico.banco.listar_projetos(), self.servico.banco.listar_tags())
        if dlg.exec() == QDialog.Accepted:
            nome, criterios = dlg.resultado()
            f = self.servico.criar_filtro(nome, criterios)
            self.lista_atual = chave_filtro(f.id)
            self.atualizar()

    def _menu_da_barra(self, pos):
        item = self.barra.itemAt(pos)
        if item is None:
            return
        tipo, chave = item.data(PAPEL_TIPO), item.data(PAPEL_CHAVE)
        menu = QMenu(self)
        if tipo in ("projeto", "arquivada"):
            menu.addAction("Editar lista...", lambda: self.editar_projeto(chave))
            menu.addAction("Renomear...", lambda: self.renomear_projeto(chave))
            cores = menu.addMenu("Cor")
            for cor in CORES_LISTAS:
                pm = QPixmap(14, 14)
                pm.fill(QColor(cor))
                cores.addAction(QIcon(pm), cor.upper(), lambda c=cor: self.trocar_cor_projeto(chave, c))
            menu.addAction("Mover para pasta...", lambda: self.pasta_do_projeto(chave))
            if tipo == "projeto":
                menu.addAction("Subir", lambda: self.mover_projeto(chave, -1))
                menu.addAction("Descer", lambda: self.mover_projeto(chave, +1))
                menu.addAction("Arquivar", lambda: self.arquivar_projeto(chave))
            else:
                menu.addAction("Desarquivar", lambda: self.arquivar_projeto(chave, False))
            menu.addSeparator()
            menu.addAction("Apagar lista...", lambda: self.apagar_projeto(chave))
        elif tipo == "etiqueta":
            nome = chave[len(PREFIXO_TAG):]
            menu.addAction("Renomear...", lambda: self.renomear_tag(nome))
            cores = menu.addMenu("Cor")
            for cor in CORES_LISTAS:
                pm = QPixmap(14, 14)
                pm.fill(QColor(cor))
                cores.addAction(QIcon(pm), cor.upper(), lambda c=cor: self.trocar_cor_tag(nome, c))
            menu.addAction("Mesclar com...", lambda: self.mesclar_tag(nome))
            menu.addSeparator()
            menu.addAction("Apagar etiqueta...", lambda: self.apagar_tag(nome))
        elif tipo == "filtro":
            menu.addAction("Renomear...", lambda: self.renomear_filtro(chave))
            menu.addAction("Excluir filtro", lambda: self.excluir_filtro(chave))
        else:
            return
        menu.exec(self.barra.mapToGlobal(pos))

    # ---- listas (projetos) ----
    def renomear_projeto(self, projeto_id: int, nome: str | None = None):
        if nome is None:
            atual = self.servico.banco.obter_projeto(projeto_id).nome
            nome, ok = QInputDialog.getText(self, "Renomear lista", "Novo nome:", text=atual)
            if not ok:
                return
        if nome.strip():
            self.servico.renomear_projeto(projeto_id, nome)
            self.atualizar(manter_selecao=True)

    def pasta_do_projeto(self, projeto_id: int, pasta: str | None = None):
        if pasta is None:
            atual = self.servico.banco.obter_projeto(projeto_id).pasta
            existentes = sorted({p.pasta for p in self.servico.banco.listar_projetos() if p.pasta}, key=str.lower)
            pasta, ok = QInputDialog.getItem(self, "Pasta da lista", "Nome da pasta (vazio = sem pasta):",
                                             [""] + existentes, max(existentes.index(atual) + 1, 0)
                                             if atual in existentes else 0, True)
            if not ok:
                return
        self.servico.definir_pasta_projeto(projeto_id, pasta)
        self.atualizar(manter_selecao=True)

    def trocar_cor_projeto(self, projeto_id: int, cor: str):
        self.servico.definir_cor_projeto(projeto_id, cor)
        self.atualizar(manter_selecao=True)

    def mover_projeto(self, projeto_id: int, passo: int):
        ids = [p.id for p in self.servico.banco.listar_projetos()]
        i = ids.index(projeto_id)
        j = i + passo
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
            self.servico.reordenar_projetos(ids)
            self.atualizar(manter_selecao=True)

    def arquivar_projeto(self, projeto_id: int, arquivar: bool = True):
        self.servico.arquivar_projeto(projeto_id, arquivar)
        if arquivar and self.lista_atual == projeto_id:
            self.lista_atual = HOJE
        self.atualizar()

    def apagar_projeto(self, projeto_id: int, confirmar: bool = True):
        if confirmar:
            nome = self.servico.banco.obter_projeto(projeto_id).nome
            r = QMessageBox.question(
                self, "Apagar lista", f"Apagar a lista “{nome}”? As tarefas dela vão para a lixeira.")
            if r != QMessageBox.Yes:
                return
        self.servico.apagar_projeto(projeto_id)
        if self.lista_atual == projeto_id:
            self.lista_atual = HOJE
        self.atualizar()

    # ---- etiquetas ----
    def renomear_tag(self, nome: str, novo: str | None = None):
        if novo is None:
            novo, ok = QInputDialog.getText(self, "Renomear etiqueta", "Novo nome:", text=nome)
            if not ok:
                return
        if novo.strip().lstrip("#"):
            self.servico.renomear_tag(nome, novo)
            if self.lista_atual == chave_tag(nome):
                self.lista_atual = chave_tag(novo.strip().lstrip("#").lower())
            self.atualizar(manter_selecao=True)

    def trocar_cor_tag(self, nome: str, cor: str):
        self.servico.definir_cor_tag(nome, cor)
        self.atualizar(manter_selecao=True)

    def mesclar_tag(self, nome: str, destino: str | None = None):
        if destino is None:
            outras = [g.nome for g in self.servico.banco.listar_tags() if g.nome != nome]
            if not outras:
                return
            destino, ok = QInputDialog.getItem(self, "Mesclar etiquetas",
                                               f"Juntar “{nome}” com:", outras, 0, False)
            if not ok:
                return
        self.servico.mesclar_tags(nome, destino)
        if self.lista_atual == chave_tag(nome):
            self.lista_atual = chave_tag(destino)
        self.atualizar(manter_selecao=True)

    def apagar_tag(self, nome: str, confirmar: bool = True):
        if confirmar:
            r = QMessageBox.question(
                self, "Apagar etiqueta", f"Apagar a etiqueta “{nome}”? Ela sai de todas as tarefas.")
            if r != QMessageBox.Yes:
                return
        self.servico.apagar_tag(nome)
        if self.lista_atual == chave_tag(nome):
            self.lista_atual = HOJE
        self.atualizar()

    # ---- filtros ----
    def renomear_filtro(self, chave: str, nome: str | None = None):
        filtro_id = int(chave[len(PREFIXO_FILTRO):])
        if nome is None:
            atual = self.servico.banco.obter_filtro(filtro_id).nome
            nome, ok = QInputDialog.getText(self, "Renomear filtro", "Novo nome:", text=atual)
            if not ok:
                return
        self.servico.renomear_filtro(filtro_id, nome)
        self.atualizar(manter_selecao=True)

    def excluir_filtro(self, chave: str):
        self.servico.apagar_filtro(int(chave[len(PREFIXO_FILTRO):]))
        if self.lista_atual == chave:
            self.lista_atual = HOJE
        self.atualizar()

    def aplicar_ordem_da_lista(self):
        """Depois de arrastar: grava a ordem que ficou na tela."""
        ids = [self.tarefas.item(i).data(PAPEL_TAREFA).id for i in range(self.tarefas.count())
               if self.tarefas.item(i).data(PAPEL_TAREFA) is not None]
        self.servico.reordenar(ids)
        self.atualizar(manter_selecao=True)

    # ---- atualização da tela ----
    def _trocar_visao_da_lista(self, nova):
        """Cada lista lembra como abre (lista, Kanban ou linha do tempo); as listas inteligentes usam a escolha geral."""
        if not isinstance(self.lista_atual, int):
            self._visao_geral = self.visao_atual
        if isinstance(nova, int):
            p = self.servico.banco.obter_projeto(nova)
            if p is not None:
                self.visao_atual = p.visao
        else:
            self.visao_atual = getattr(self, "_visao_geral", self.visao_atual)

    def selecionar_lista(self, chave):
        if chave != self.lista_atual:
            self._trocar_visao_da_lista(chave)
        self.lista_atual = chave
        if chave != BUSCA and self.btn_busca.isChecked():
            self.btn_busca.setChecked(False)
        self.atualizar()

    def _ao_trocar_lista(self, atual, _anterior):
        if atual is None or atual.data(PAPEL_TIPO) in ("cabecalho", "dica", "divisor"):
            return
        chave = atual.data(PAPEL_CHAVE)
        if chave != self.lista_atual:
            self._trocar_visao_da_lista(chave)
            self.lista_atual = chave
            if self.btn_busca.isChecked():
                self.btn_busca.blockSignals(True)
                self.btn_busca.setChecked(False)
                self.btn_busca.blockSignals(False)
                self.busca.setVisible(False)
                self.busca.clear()
            self.atualizar()

    def _ativou_tarefa(self, item):
        """Enter na lista (ou duplo clique pelo teclado) abre o cartão da tarefa."""
        t = item.data(PAPEL_TAREFA) if item is not None else None
        if t is not None:
            r = self.tarefas.visualItemRect(item)
            self.abrir_cartao_da_tarefa(t.id, QRect(self.tarefas.viewport().mapToGlobal(r.topLeft()), r.size()),
                                        foco=True)

    def _ao_selecionar_tarefa(self, atual, _anterior):
        t = atual.data(PAPEL_TAREFA) if atual else None
        self._selecionada = t.id if t is not None else None
        self._mostrar_detalhe(t)

    def id_selecionado(self) -> int | None:
        return self._selecionada

    def selecionar_tarefa(self, tarefa_id: int | None):
        """Mostra a tarefa no painel de detalhe (usado pelas telas de calendário, quadro e matriz)."""
        self._selecionada = tarefa_id
        t = self.servico.banco.obter_tarefa(tarefa_id) if tarefa_id is not None else None
        if t is not None:
            for i in range(self.tarefas.count()):
                dado = self.tarefas.item(i).data(PAPEL_TAREFA)
                if dado is not None and dado.id == tarefa_id:
                    self.tarefas.blockSignals(True)
                    self.tarefas.setCurrentRow(i)
                    self.tarefas.blockSignals(False)
                    break
        self._mostrar_detalhe(t)
        if self.visao_atual == "linha_tempo" and self.pagina_atual == "tarefas":
            self.linha_tempo.quadro.selecionada = tarefa_id
            self.linha_tempo.quadro.update()

    def _ordenar(self, tarefas: list[Tarefa]) -> list[Tarefa]:
        if self.ordem_atual == "prioridade":
            res = sorted(tarefas, key=lambda t: -int(t.prioridade))
        elif self.ordem_atual == "titulo":
            res = sorted(tarefas, key=lambda t: t.titulo.lower())
        elif self.ordem_atual == "criacao":
            res = sorted(tarefas, key=lambda t: t.criada_em, reverse=True)
        elif self.ordem_atual == "manual":
            res = sorted(tarefas, key=lambda t: (t.ordem, t.id))
        else:
            res = list(tarefas)
        return sorted(res, key=lambda t: not t.fixada)     # fixadas sempre no topo (a ordenação é estável)

    def definir_agrupamento(self, chave: str):
        self.agrupar_atual = chave
        self.atualizar(manter_selecao=True)

    def _agrupar(self, tarefas: list[Tarefa]) -> list[tuple[str, list[Tarefa]]]:
        """[(nome do grupo, tarefas)] na ordem de exibição; dentro de cada grupo vale a ordenação atual."""
        modo, hoje = self.agrupar_atual, date.today()
        projetos = {p.id: p for p in self.servico.banco.listar_projetos()
                    + self.servico.banco.listar_projetos_arquivados()}
        grupos: dict[str, list[Tarefa]] = {}
        for t in tarefas:
            if modo == "data":
                if t.prazo is None:
                    nome = "Sem data"
                elif t.prazo < hoje:
                    nome = "Atrasadas"
                elif t.prazo == hoje:
                    nome = "Hoje"
                elif t.prazo == hoje + timedelta(days=1):
                    nome = "Amanhã"
                elif t.prazo <= hoje + timedelta(days=7):
                    nome = "Próximos 7 dias"
                else:
                    nome = "Mais tarde"
            elif modo == "projeto":
                nome = projetos[t.projeto_id].nome if t.projeto_id in projetos else "Caixa de Entrada"
            elif modo == "prioridade":
                nome = tema.NOME_PRIORIDADE[int(t.prioridade)]
            else:  # etiqueta
                nome = "#" + t.tags[0] if t.tags else "Sem etiqueta"
            grupos.setdefault(nome, []).append(t)
        if modo == "data":
            chaves = [g for g in GRUPOS_DE_DATA if g in grupos]
        elif modo == "projeto":
            ordem = ["Caixa de Entrada"] + [p.nome for p in projetos.values()]
            chaves = sorted(grupos, key=lambda n: ordem.index(n) if n in ordem else len(ordem))
        elif modo == "prioridade":
            chaves = [tema.NOME_PRIORIDADE[v] for v in (3, 2, 1, 0) if tema.NOME_PRIORIDADE[v] in grupos]
        else:
            chaves = sorted(grupos, key=lambda n: (n == "Sem etiqueta", n))
        return [(c, grupos[c]) for c in chaves]

    def _tarefas_da_tela(self) -> list[Tarefa]:
        if self.btn_busca.isChecked():
            return self.servico.buscar(self.busca.text())
        return self._ordenar(self.servico.listar(self.lista_atual))

    def _agrupando(self) -> bool:
        return self.agrupar_atual != "nenhum" and self.lista_atual not in (CONCLUIDAS, LIXEIRA)

    def atualizar(self, selecionar_id: int | None = None, manter_selecao: bool = False):
        anterior = self._selecionada if manter_selecao else None
        alvo = selecionar_id or anterior

        contagens = self.servico.contagens()
        projetos = self.servico.banco.listar_projetos()
        arquivados = self.servico.banco.listar_projetos_arquivados()
        etiquetas = self.servico.banco.listar_tags()
        self.delegado.projetos = {p.id: p for p in projetos + arquivados}
        self.delegado.cores_tags = {g.nome: g.cor for g in etiquetas if g.cor != "#8a8f98"}
        self.delegado.progressos = self.servico.progressos()
        filtros_salvos = self.servico.banco.listar_filtros()
        self.delegado.mostrar_projeto = not isinstance(self.lista_atual, int)

        self.barra.blockSignals(True)
        self.barra.clear()
        escolhido = None

        def adicionar(tipo, chave, texto, cor=None, icone=None, rotulo=None):
            nonlocal escolhido
            item = QListWidgetItem(texto)
            item.setData(PAPEL_TIPO, tipo)
            item.setData(PAPEL_CHAVE, chave)
            if tipo in ("lista", "projeto", "arquivada", "etiqueta", "filtro"):
                item.setData(PAPEL_CONTAGEM, contagens.get(chave, 0))
            if cor:
                item.setData(PAPEL_COR, cor)
            if icone:
                item.setData(PAPEL_ICONE, icone)
            if rotulo:
                item.setData(PAPEL_ROTULO_ICONE, rotulo)
            if tipo in ("cabecalho", "dica", "divisor"):
                item.setFlags(Qt.NoItemFlags)
            self.barra.addItem(item)
            if tipo in ("lista", "projeto", "arquivada", "etiqueta", "filtro") and chave == self.lista_atual:
                escolhido = item
            return item

        adicionar("lista", TODAS, "Todas", icone="todas")
        adicionar("lista", HOJE, "Hoje", icone="hoje", rotulo=str(date.today().day))
        adicionar("lista", AMANHA, "Amanhã", icone="hoje", rotulo=str((date.today() + timedelta(days=1)).day))
        adicionar("lista", PROXIMOS, "Próximos 7 dias", icone="proximos", rotulo="7")
        adicionar("lista", CAIXA, "Caixa de Entrada", icone="caixa")
        adicionar("divisor", None, "")
        def adicionar_projeto(p):
            it = adicionar("projeto", p.id, p.nome, p.cor, icone="lista")
            if p.emoji:
                it.setData(PAPEL_EMOJI, p.emoji)

        adicionar("cabecalho", "novo:lista", "Listas").setFlags(Qt.ItemIsEnabled)
        for p in projetos:
            if not p.pasta:
                adicionar_projeto(p)
        for pasta in sorted({p.pasta for p in projetos if p.pasta}, key=str.lower):
            adicionar("cabecalho", None, pasta)
            for p in projetos:
                if p.pasta == pasta:
                    adicionar_projeto(p)
        if arquivados:
            adicionar("cabecalho", None, "Listas arquivadas")
            for p in arquivados:
                adicionar("arquivada", p.id, p.nome, p.cor, icone="lista")
        adicionar("cabecalho", "novo:etiqueta", "Etiquetas").setFlags(Qt.ItemIsEnabled)
        if etiquetas:
            for g in etiquetas:
                adicionar("etiqueta", chave_tag(g.nome), g.nome, g.cor if g.cor != "#8a8f98" else None, icone="etiqueta")
        else:
            adicionar("dica", None, "Categorize suas tarefas com etiquetas. "
                      "Digite # ao adicionar uma tarefa, por exemplo #casa.")
        adicionar("cabecalho", "novo:filtro", "Filtros").setFlags(Qt.ItemIsEnabled)
        if filtros_salvos:
            for f in filtros_salvos:
                adicionar("filtro", chave_filtro(f.id), f.nome, icone="filtro")
        else:
            adicionar("dica", None, "Crie filtros por lista, data, prioridade ou etiqueta "
                      "com o “+” ao lado de Filtros.")
        adicionar("divisor", None, "")
        adicionar("lista", CONCLUIDAS, "Concluídas", icone="concluido")
        adicionar("lista", LIXEIRA, "Lixeira", icone="lixeira")
        if escolhido and not self.btn_busca.isChecked():
            self.barra.setCurrentItem(escolhido)
        self.barra.blockSignals(False)

        # cabeçalho central
        if self.btn_busca.isChecked():
            nome = TITULOS[BUSCA]
        elif isinstance(self.lista_atual, int):
            nome = next((f"{p.emoji} {p.nome}".strip() for p in projetos + arquivados if p.id == self.lista_atual),
                        "Lista")
        elif self.lista_atual.startswith(PREFIXO_TAG):
            nome = "#" + self.lista_atual[len(PREFIXO_TAG):]
        elif self.lista_atual.startswith(PREFIXO_FILTRO):
            nome = next((f.nome for f in filtros_salvos if chave_filtro(f.id) == self.lista_atual), "Filtro")
        else:
            nome = TITULOS[self.lista_atual]
        self.titulo.setText(nome)

        # lista
        pode_arrastar = (self.ordem_atual == "manual" and not self.btn_busca.isChecked()
                         and self.lista_atual not in (CONCLUIDAS, LIXEIRA) and not self._agrupando())
        self.tarefas.permitir_arrastar(pode_arrastar)
        self.tarefas.blockSignals(True)
        self.tarefas.clear()
        da_tela = self._tarefas_da_tela()
        if self._agrupando():
            for nome_grupo, membros in self._agrupar(da_tela):
                cab = QListWidgetItem(nome_grupo)
                cab.setData(PAPEL_TIPO, "grupo")
                cab.setData(PAPEL_CONTAGEM, len(membros))
                cab.setFlags(Qt.NoItemFlags)
                self.tarefas.addItem(cab)
                for t in membros:
                    item = QListWidgetItem()
                    item.setData(PAPEL_TAREFA, t)
                    self.tarefas.addItem(item)
        else:
            for t in da_tela:
                item = QListWidgetItem()
                item.setData(PAPEL_TAREFA, t)
                self.tarefas.addItem(item)
        self.tarefas.blockSignals(False)
        vazio = len(da_tela) == 0
        em_lista = self.visao_atual == "lista"
        self.tarefas.setVisible(em_lista and not vazio)
        self.vazio.setVisible(em_lista and vazio)
        self.vazio.setText("Nenhum resultado." if self.btn_busca.isChecked() else "Nada por aqui.")
        self.kanban.setVisible(self.visao_atual == "kanban")
        self.linha_tempo.setVisible(self.visao_atual == "linha_tempo")
        self.btn_ordenar.setVisible(em_lista)
        self._da_tela = da_tela

        selecionado = None
        if alvo:
            for i in range(self.tarefas.count()):
                dado = self.tarefas.item(i).data(PAPEL_TAREFA)
                if dado is not None and dado.id == alvo:
                    selecionado = self.tarefas.item(i)
                    break
        if selecionado:
            self.tarefas.setCurrentItem(selecionado)
            self._selecionada = alvo
            self._mostrar_detalhe(selecionado.data(PAPEL_TAREFA))
        else:
            self.tarefas.blockSignals(True)
            self.tarefas.setCurrentItem(None)
            self.tarefas.blockSignals(False)
            externa = None
            if alvo and (self.pagina_atual != "tarefas" or self.visao_atual != "lista"):
                externa = self.servico.banco.obter_tarefa(alvo)
                if externa is not None and externa.apagada_em is not None:
                    externa = None
            self._selecionada = externa.id if externa is not None else None
            self._mostrar_detalhe(externa)
        self.atualizar_paginas()
        self._ajustar_paineis()

    def atualizar_paginas(self):
        """Redesenha a tela que está aparecendo (as outras se atualizam quando você chegar nelas)."""
        pag = self.pagina_atual
        if pag == "tarefas":
            if self.visao_atual == "kanban":
                self.kanban.carregar(self._da_tela)
            elif self.visao_atual == "linha_tempo":
                self.linha_tempo.carregar(self._da_tela)
        elif pag == "calendario":
            self.pagina_calendario.atualizar()
        elif pag == "matriz":
            self.pagina_matriz.atualizar()
        elif pag == "foco":
            self.pagina_foco.atualizar()
        elif pag == "habitos":
            self.pagina_habitos.atualizar()
        elif pag == "contagem":
            self.pagina_contagem.atualizar()
        elif pag == "estatisticas":
            self.pagina_estatisticas.atualizar()

    # ---- páginas e visões ----
    def mostrar_pagina(self, chave: str):
        if chave not in self.paginas:
            return
        self.pagina_atual = chave
        self.pilha_paginas.setCurrentWidget(self.paginas[chave])
        self.btns_pagina[chave].setChecked(True)
        self.barra_caixa.setVisible(chave == "tarefas" and self._barra_visivel)
        self._ajustar_paineis()
        if chave != "tarefas" and self.btn_busca.isChecked():
            self.btn_busca.blockSignals(True)
            self.btn_busca.setChecked(False)
            self.btn_busca.blockSignals(False)
            self.busca.setVisible(False)
            self.busca.clear()
        self.atualizar(manter_selecao=True)

    PAGINAS_COM_CARTAO = ("tarefas", "matriz")      # nestas, editar abre o cartão flutuante (não o painel)

    def _detalhe_visivel(self, chave: str) -> bool:
        if chave in PAGINAS_SEM_DETALHE:
            return False
        return bool(self.prefs.get("detalhe_lateral", False)) or chave not in self.PAGINAS_COM_CARTAO

    def definir_detalhe_lateral(self, ligado: bool):
        """Liga ou desliga o painel de detalhes fixo na lateral (por padrão, editar abre o cartão flutuante)."""
        self.aplicar_preferencias({"detalhe_lateral": bool(ligado)})
        self._ajustar_paineis()
        self._mostrar_detalhe(self.servico.banco.obter_tarefa(self._selecionada) if self._selecionada else None)

    # ---- cartão ampliado na lateral (modo lista) ----
    def cartao_acoplado_ativo(self) -> bool:
        return self.pagina_atual == "tarefas" and self.visao_atual == "lista" and not self.bool_lateral()

    def _ajustar_paineis(self):
        acoplado = self.cartao_acoplado_ativo()
        self.painel_cartao.setVisible(acoplado)
        self.detalhe.setVisible(self._detalhe_visivel(self.pagina_atual))

    @staticmethod
    def _assinatura(t) -> tuple:
        return (t.titulo, t.notas, t.prazo, t.prazo_hora, t.concluida, int(t.prioridade), t.projeto_id,
                tuple(t.tags), t.inicio, t.duracao_min, tuple(t.lembretes), t.repeticao)

    def _mostrar_detalhe(self, t):
        """Atualiza o painel de detalhe antigo (escondido) e, no modo lista, o cartão ampliado da lateral."""
        self.detalhe.mostrar(t)
        if not self.cartao_acoplado_ativo():
            return
        atual = self.cartao_acoplado
        if t is None:
            self._descartar_cartao_acoplado()
            return
        if atual is not None and atual.t is not None and atual.t.id == t.id:
            if atual.pendente or atual.titulo.hasFocus() or atual.notas.hasFocus() \
                    or self._assinatura(atual.t) == self._assinatura(t):
                return                          # está sendo editado, ou já está igual: não mexe
        self._descartar_cartao_acoplado()
        c = CartaoTarefa(self, tarefa=t, acoplado=True)
        c.salvou.connect(lambda nova: self.atualizar(selecionar_id=nova.id if nova is not None else None,
                                                     manter_selecao=nova is None))
        self.cartao_acoplado = c
        self.painel_cartao.layout().insertWidget(0, c, 1)
        self.vazio_cartao.setVisible(False)
        c.show()

    def _descartar_cartao_acoplado(self):
        c = self.cartao_acoplado
        self.cartao_acoplado = None
        if c is not None:
            if c.pendente:
                c.gravar_agora(emitir=False)
                self.pedir_atualizacao()
            c._feito = True                     # daqui em diante não grava mais
            c.setParent(None)
            c.deleteLater()
        self.vazio_cartao.setVisible(True)

    def pedir_atualizacao(self):
        """Refaz a lista logo depois do evento atual (evita atualizar no meio de uma atualização)."""
        QTimer.singleShot(0, lambda: self.atualizar(manter_selecao=True))

    # ---- cartão flutuante de edição (igual ao do calendário) ----
    def abrir_cartao_da_tarefa(self, tarefa_id: int, alvo: QRect | None = None,
                               foco: bool = False) -> CartaoTarefa | None:
        t = self.servico.banco.obter_tarefa(tarefa_id)
        if t is None or t.apagada_em is not None:
            return None
        self.selecionar_tarefa(tarefa_id)
        if self.bool_lateral():
            return None
        if self.cartao_acoplado_ativo():
            if self.cartao_acoplado is not None and foco:
                self.cartao_acoplado.titulo.setFocus()
            return self.cartao_acoplado
        antigo = getattr(self, "cartao_aberto", None)
        if antigo is not None:
            try:
                antigo.close()
            except RuntimeError:
                pass
        c = CartaoTarefa(self, tarefa=t)
        c.salvou.connect(lambda nova: self.atualizar(selecionar_id=nova.id if nova is not None else None,
                                                     manter_selecao=nova is None))
        self.cartao_aberto = c
        QToolTip.hideText()
        c.mostrar_perto(QCursor.pos(), alvo)
        c.titulo.setFocus()
        return c

    def bool_lateral(self) -> bool:
        """Com o painel lateral ligado, clicar só seleciona (o painel já mostra a tarefa)."""
        return bool(self.prefs.get("detalhe_lateral", False))

    def alternar_barra(self):
        self._barra_visivel = not self._barra_visivel
        self.barra_caixa.setVisible(self._barra_visivel and self.pagina_atual == "tarefas")

    def definir_visao(self, chave: str):
        if chave not in dict(VISOES):
            return
        self.visao_atual = chave
        if isinstance(self.lista_atual, int):
            self.servico.definir_visao_projeto(self.lista_atual, chave)
        else:
            self._visao_geral = chave
        if self.pagina_atual != "tarefas":
            self.mostrar_pagina("tarefas")
        else:
            self.atualizar(manter_selecao=True)

    def _menu_visao(self):
        menu = QMenu(self)
        for chave, nome in VISOES:
            a = menu.addAction(nome, lambda c=chave: self.definir_visao(c))
            a.setCheckable(True)
            a.setChecked(chave == self.visao_atual)
        menu.exec(self.btn_visao.mapToGlobal(self.btn_visao.rect().bottomLeft()))

    def _menu_config(self):
        menu = QMenu(self)
        for chave, _icone, dica in PAGINAS:
            if chave in SECUNDARIAS:
                menu.addAction(dica, lambda c=chave: self.mostrar_pagina(c))
        menu.addSeparator()
        menu.addAction("Configurações...", self.abrir_configuracoes)
        menu.addAction("Configurações de IA...", self.abrir_config_ia)
        menu.addAction("Integrações (Google Calendar)...", self.abrir_integracoes)
        menu.addAction("Backup, importar e exportar...", self.abrir_dados)
        menu.addAction("Sincronizar agora", self.sincronizar_agora)
        lateral = menu.addAction("Painel lateral de detalhes (em vez do cartão)", self.definir_detalhe_lateral)
        lateral.setCheckable(True)
        lateral.setChecked(self.bool_lateral())
        menu.addSeparator()
        menu.addAction("Atalhos de teclado", self.mostrar_atalhos)
        menu.addAction("Central de ajuda", self.mostrar_ajuda)
        origem = self.sender() if isinstance(self.sender(), QPushButton) else self.btn_config
        menu.exec(origem.mapToGlobal(origem.rect().topRight()))

    def mostrar_ajuda(self):
        QMessageBox.information(
            self, "Central de ajuda",
            "Adicionar rápido: digite o título com data, hora, prioridade, etiqueta e lista, por exemplo "
            "“Reunião amanhã 9h !2 #trabalho”.\n\n"
            "Ctrl+K busca tarefas, listas, etiquetas e filtros. Clique com o botão direito em uma tarefa ou "
            "lista para ver mais ações. F1 mostra todos os atalhos.\n\n"
            "Os dados ficam só no seu computador (e no servidor de sincronização, se você ligar).")

    def abrir_calendarios_externos(self):
        """Calendários por link (.ics)."""
        dlg = DialogoAssinaturas(self, self.servico)
        dlg.exec()
        if dlg.mudou:
            self.atualizar(manter_selecao=True)

    def abrir_config_ia(self):
        self.pagina_ia.configurar()

    def abrir_integracoes(self):
        dlg = DialogoIntegracoes(self, self.abrir_google, self.abrir_calendarios_externos)
        dlg.exec()

    def abrir_google(self):
        dlg = DialogoGoogle(self, self.servico, self.gerente_google)
        dlg.exec()
        self.atualizar(manter_selecao=True)

    def _google_terminou(self, resumo):
        if resumo.erro:
            self._atualizar_icone_sync("erro", f"Google Calendar: {resumo.erro}")
        if resumo.total_mudancas():
            if self.detalhe.tarefa is not None:
                self.detalhe._salvar()
            self.pedir_atualizacao()

    def abrir_dados(self):
        dlg = DialogoDados(self, self.servico, ao_mudar=lambda: self.atualizar())
        dlg.exec()

    def abrir_tarefa_rapida(self):
        self.janela_rapida.mostrar()

    # ---- sugestão de subtarefas (Claude) ----
    def sugerir_subtarefas(self, tarefa_id: int):
        t = self.servico.banco.obter_tarefa(tarefa_id)
        if t is None or self._ia_ocupada:
            return
        cfg = self.servico.ia
        usar_nova = cfg.tem_chave()
        chave = "" if usar_nova else ia.chave_da_api(self.prefs)
        if not usar_nova and not chave:
            QMessageBox.information(self, "IA", "Para usar esta função, escolha uma IA e cole a chave em "
                                    "Configurações de IA (engrenagem). Só o título e as notas da tarefa são "
                                    "enviados, e só quando você clica no botão.")
            return
        titulo, notas, modelo = t.titulo, t.notas, (self.prefs.get("claude_modelo") or None)
        self._ia_ocupada = True
        self.detalhe.btn_ia.setEnabled(False)
        self.detalhe.btn_ia.setText("Pensando...")
        if usar_nova:
            pedido = cfg.pedido()
            funcao = lambda: ia_provedores.quebrar_tarefa(pedido, titulo, notas)      # noqa: E731
        else:
            funcao = lambda: self._ia_quebrar(titulo, notas, chave, modelo)      # noqa: E731
        if self._ia_em_thread:
            QThreadPool.globalInstance().start(_TrabalhoIA(tarefa_id, funcao, self._sinais_ia))
        else:
            try:
                self._fim_ia(tarefa_id, funcao(), None)
            except Exception as e:  # noqa: BLE001
                self._fim_ia(tarefa_id, None, e)

    def _fim_ia(self, tarefa_id: int, subtarefas, erro):
        self._ia_ocupada = False
        self.detalhe.btn_ia.setEnabled(True)
        self.detalhe.btn_ia.setText("Sugerir subtarefas com IA")
        if erro is not None:
            QMessageBox.warning(self, "IA", str(erro))
            return
        criadas = 0
        for texto in subtarefas:
            try:
                self.servico.adicionar_subtarefa(tarefa_id, texto)
                criadas += 1
            except ValueError:
                break
        self.atualizar(manter_selecao=True)
        self.notificador("Subtarefas sugeridas", f"{criadas} subtarefa(s) adicionada(s). Revise e apague o que não servir.")

    # ---- foco e modelos ----
    def iniciar_foco_na_tarefa(self, tarefa_id: int):
        self.mostrar_pagina("foco")
        self.pagina_foco.escolher_tarefa(tarefa_id)
        if not self.pagina_foco.cron.ativo:
            self.pagina_foco.iniciar()

    def salvar_modelo(self, tarefa_id: int, nome: str | None = None):
        t = self.servico.banco.obter_tarefa(tarefa_id)
        if t is None:
            return
        if nome is None:
            nome, ok = QInputDialog.getText(self, "Salvar como modelo", "Nome do modelo:", text=t.titulo)
            if not ok or not nome.strip():
                return
        self.servico.modelos.salvar_de_tarefa(tarefa_id, nome)
        self.notificador("Modelo salvo", f"“{nome.strip()}” (com as subtarefas) está em Modelos.")

    def criar_de_modelo(self, uuid: str):
        projeto = self.lista_atual if isinstance(self.lista_atual, int) else None
        t = self.servico.modelos.criar_tarefa(uuid, projeto)
        if self.pagina_atual != "tarefas":
            self.mostrar_pagina("tarefas")
        if self.lista_atual in (CONCLUIDAS, LIXEIRA, BUSCA):
            self.lista_atual = CAIXA
        self.atualizar(selecionar_id=t.id)

    def _menu_modelos(self):
        menu = QMenu(self)
        modelos = self.servico.modelos.listar()
        if not modelos:
            menu.addAction("Nenhum modelo salvo (use “Salvar como modelo” numa tarefa)").setEnabled(False)
        else:
            criar = menu.addMenu("Criar tarefa a partir de")
            for m in modelos:
                criar.addAction(m.nome, lambda u=m.uuid: self.criar_de_modelo(u))
            apagar = menu.addMenu("Apagar modelo")
            for m in modelos:
                apagar.addAction(m.nome, lambda u=m.uuid: self.servico.modelos.apagar(u))
        menu.exec(self.btn_modelos.mapToGlobal(self.btn_modelos.rect().bottomLeft()))
