"""Assistente de IA: página de chat e janela de configuração (escolha da IA, chave, modelo e privacidade)."""
from __future__ import annotations

import base64
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QImage, QKeyEvent, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMenu, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
                               QVBoxLayout, QWidget)

from ..core import assistente as ass
from ..core.arquivos_ia import MAX_ANEXOS, Anexo, carregar_arquivo, carregar_bytes, wav_de_pcm16
from ..core.ia import ErroIA
from ..core.ia_provedores import (PROVEDORES, preparar_anexos, testar_conexao, transcrever, transporte_http,
                                  transporte_multipart)
from . import icones, tema
from .voz import BarraGravacao, FonteQt, Gravador

LADO_MAX_IMAGEM = 2048          # imagens maiores que isso são reduzidas antes de ir para a IA
BYTES_REDUZIR = 3 * 1024 * 1024

SUGESTOES = [("Planejar meu dia", "Planeje o meu dia de hoje com base nas minhas tarefas e na minha agenda."),
             ("O que está atrasado?", "O que está atrasado? Sugira como reagendar."),
             ("Organizar minha semana", "Organize a minha semana: distribua as tarefas pelos dias sem sobrecarregar."),
             ("Analisar minha rotina", "Analise a minha rotina com as estatísticas e me diga o que posso melhorar.")]


class _Sinais(QObject):
    pronto = Signal(object, object)


class _Trabalho(QRunnable):
    def __init__(self, funcao, sinais: _Sinais):
        super().__init__()
        self.funcao, self.sinais = funcao, sinais

    def run(self):
        try:
            self.sinais.pronto.emit(self.funcao(), None)
        except Exception as e:  # noqa: BLE001 - qualquer falha vira mensagem na tela
            self.sinais.pronto.emit(None, e)


def _rodar(em_thread: bool, funcao, sinais: _Sinais, direto) -> None:
    if em_thread:
        QThreadPool.globalInstance().start(_Trabalho(funcao, sinais))
        return
    try:
        direto(funcao(), None)
    except Exception as e:  # noqa: BLE001
        direto(None, e)


# ---------------------------------------------------------------- configuração
class DialogoIA(QDialog):
    """Escolher a IA, colar a chave (ela nunca mais aparece), modelo opcional, privacidade e preferências."""

    def __init__(self, parent, servico, transporte=transporte_http, em_thread: bool = True):
        super().__init__(parent)
        self.servico, self.cfg = servico, servico.ia
        self.transporte, self.em_thread = transporte, em_thread
        self.setWindowTitle("Configurações de IA")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)

        lay.addWidget(QLabel("<b>Qual IA o assistente vai usar?</b>"))
        self.combo = QComboBox()
        for chave, p in PROVEDORES.items():
            if not p.so_voz:
                self.combo.addItem(p.rotulo, chave)
        self.combo.setCurrentIndex(self.combo.findData(self.cfg.ativo))
        lay.addWidget(self.combo)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setObjectName("mensagemVazia")
        lay.addWidget(self.info)

        lay.addWidget(QLabel("Chave de API"))
        linha = QHBoxLayout()
        self.campo_chave = QLineEdit()
        self.campo_chave.setEchoMode(QLineEdit.Password)
        self.campo_chave.setPlaceholderText("Cole a chave aqui. Ela só aparece agora.")
        self.btn_salvar = QPushButton("Salvar chave")
        self.btn_apagar = QPushButton("Apagar chave")
        linha.addWidget(self.campo_chave, 1)
        linha.addWidget(self.btn_salvar)
        linha.addWidget(self.btn_apagar)
        lay.addLayout(linha)
        self.estado_chave = QLabel("")
        lay.addWidget(self.estado_chave)

        lay.addWidget(QLabel("<b>Quem transcreve a sua voz?</b>"))
        self.combo_voz = QComboBox()
        self.combo_voz.addItem("Automático (a IA do chat, se ela transcrever)", "")
        for chave, p in PROVEDORES.items():
            if p.voz:
                self.combo_voz.addItem(p.rotulo, chave)
        self.combo_voz.setCurrentIndex(max(0, self.combo_voz.findData(self.cfg.voz_escolhida)))
        lay.addWidget(self.combo_voz)
        self.info_voz = QLabel("")
        self.info_voz.setWordWrap(True)
        self.info_voz.setObjectName("mensagemVazia")
        lay.addWidget(self.info_voz)
        self.caixa_voz = QWidget()
        lay_v = QHBoxLayout(self.caixa_voz)
        lay_v.setContentsMargins(0, 0, 0, 0)
        self.campo_chave_voz = QLineEdit()
        self.campo_chave_voz.setEchoMode(QLineEdit.Password)
        self.campo_chave_voz.setPlaceholderText("Cole a chave da voz aqui. Ela só aparece agora.")
        self.btn_salvar_voz = QPushButton("Salvar chave")
        self.btn_apagar_voz = QPushButton("Apagar chave")
        lay_v.addWidget(self.campo_chave_voz, 1)
        lay_v.addWidget(self.btn_salvar_voz)
        lay_v.addWidget(self.btn_apagar_voz)
        lay.addWidget(self.caixa_voz)

        self.btn_avancado = QPushButton("Avançado ▸")
        self.btn_avancado.setFlat(True)
        self.btn_avancado.setCheckable(True)
        lay.addWidget(self.btn_avancado, 0, Qt.AlignLeft)
        self.caixa_avancado = QWidget()
        lay_a = QVBoxLayout(self.caixa_avancado)
        lay_a.setContentsMargins(0, 0, 0, 0)
        lay_a.addWidget(QLabel("Modelo (deixe vazio para usar o padrão)"))
        self.campo_modelo = QLineEdit()
        lay_a.addWidget(self.campo_modelo)
        self.caixa_avancado.setVisible(False)
        lay.addWidget(self.caixa_avancado)

        self.chk_notas = QCheckBox("Enviar o texto das notas das tarefas para a IA")
        self.chk_notas.setChecked(self.cfg.enviar_notas)
        lay.addWidget(self.chk_notas)
        aviso = QLabel("Quando você usa o assistente, as tarefas, a agenda, o que você escreve, os arquivos e "
                       "imagens que você anexa e o áudio da voz vão para o provedor escolhido. Não coloque ali nada "
                       "que você não queira que ele veja.")
        aviso.setWordWrap(True)
        aviso.setObjectName("mensagemVazia")
        lay.addWidget(aviso)

        lay.addWidget(QLabel("Preferências fixas (uma por linha). Ex.: não marcar nada antes das 8h"))
        self.campo_pref = QPlainTextEdit("\n".join(self.cfg.preferencias))
        self.campo_pref.setObjectName("campoIA")
        self.campo_pref.setFixedHeight(80)
        lay.addWidget(self.campo_pref)

        linha2 = QHBoxLayout()
        self.btn_testar = QPushButton("Testar conexão")
        self.status = QLabel("")
        self.status.setWordWrap(True)
        linha2.addWidget(self.btn_testar)
        linha2.addWidget(self.status, 1)
        lay.addLayout(linha2)
        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.accept)
        rodape = QHBoxLayout()
        rodape.addStretch(1)
        rodape.addWidget(fechar)
        lay.addLayout(rodape)

        self._sinais = _Sinais()
        self._sinais.pronto.connect(self._fim_teste)
        self.combo.currentIndexChanged.connect(self._trocou_provedor)
        self.combo_voz.currentIndexChanged.connect(self._trocou_voz)
        self.btn_salvar_voz.clicked.connect(self.salvar_chave_voz)
        self.btn_apagar_voz.clicked.connect(self.apagar_chave_voz)
        self.btn_salvar.clicked.connect(self.salvar_chave)
        self.btn_apagar.clicked.connect(self.apagar_chave)
        self.btn_testar.clicked.connect(self.testar)
        self.btn_avancado.toggled.connect(self._alternar_avancado)
        self.campo_modelo.editingFinished.connect(self._gravar_modelo)
        self.chk_notas.toggled.connect(self.cfg.definir_enviar_notas)
        self.finished.connect(lambda _=0: self._gravar_preferencias())
        self._atualizar()

    @property
    def provedor(self) -> str:
        return self.combo.currentData()

    def _alternar_avancado(self, ligado: bool):
        self.caixa_avancado.setVisible(ligado)
        self.btn_avancado.setText("Avançado ▾" if ligado else "Avançado ▸")
        self.adjustSize()

    def _trocou_provedor(self):
        self.cfg.definir_ativo(self.provedor)
        self._atualizar()

    @property
    def provedor_voz_escolhido(self) -> str:
        return self.combo_voz.currentData()

    def _trocou_voz(self):
        self.cfg.definir_voz(self.provedor_voz_escolhido)
        self._atualizar_voz()

    def _atualizar_voz(self):
        escolhido = self.provedor_voz_escolhido
        efetivo = escolhido or self.cfg.provedor_voz()
        if not efetivo:
            self.info_voz.setText("A IA escolhida acima não transcreve voz. Escolha Gemini, ChatGPT ou Groq aqui "
                                  "para usar o microfone.")
        elif escolhido == "groq":
            p = PROVEDORES["groq"]
            self.info_voz.setText(f"{p.custo}\nOnde criar a chave: {p.onde_chave}\n{self.cfg.mascara('groq')}")
        else:
            p = PROVEDORES[efetivo]
            self.info_voz.setText(f"Usa a chave de {p.rotulo}: {self.cfg.mascara(efetivo)}")
        self.caixa_voz.setVisible(escolhido == "groq")
        self.btn_apagar_voz.setEnabled(self.cfg.tem_chave("groq"))
        self.campo_chave_voz.clear()
        self._acomodar()

    def _acomodar(self):
        """Os textos explicativos mudam de tamanho conforme a escolha: a janela cresce junto, para nada ficar cortado."""
        self.layout().activate()
        self.resize(self.width(), max(self.height(), self.layout().totalHeightForWidth(self.width())))

    def salvar_chave_voz(self):
        try:
            self.cfg.salvar_chave("groq", self.campo_chave_voz.text())
        except ErroIA as e:
            self.status.setText(str(e))
            return
        self.status.setText("Chave da voz salva.")
        self._atualizar_voz()

    def apagar_chave_voz(self):
        self.cfg.apagar_chave("groq")
        self.status.setText("Chave da voz apagada.")
        self._atualizar_voz()

    def _atualizar(self):
        p = PROVEDORES[self.provedor]
        self.info.setText(f"{p.custo}\nOnde criar a chave: {p.onde_chave}")
        self.estado_chave.setText(self.cfg.mascara(self.provedor))
        self.btn_apagar.setEnabled(self.cfg.tem_chave(self.provedor))
        self.campo_modelo.setPlaceholderText(p.modelo_padrao)
        self.campo_modelo.setText(self.cfg.modelo_personalizado(self.provedor))
        self.campo_chave.clear()
        self._atualizar_voz()                       # também reacomoda a janela

    def salvar_chave(self):
        try:
            self.cfg.salvar_chave(self.provedor, self.campo_chave.text())
        except ErroIA as e:
            self.status.setText(str(e))
            return
        self.campo_chave.clear()                    # some da tela: não dá para ver de novo
        self.status.setText("Chave salva. Clique em “Testar conexão” para conferir.")
        self._atualizar()

    def apagar_chave(self):
        self.cfg.apagar_chave(self.provedor)
        self.status.setText("Chave apagada.")
        self._atualizar()

    def _gravar_modelo(self):
        self.cfg.definir_modelo(self.provedor, self.campo_modelo.text())

    def _gravar_preferencias(self):
        self.cfg.definir_preferencias(self.campo_pref.toPlainText().splitlines())

    def testar(self):
        if not self.cfg.tem_chave(self.provedor):
            self.status.setText("Salve a chave primeiro.")
            return
        self._gravar_modelo()
        pedido = self.cfg.pedido()
        self.status.setText("Testando...")
        self.btn_testar.setEnabled(False)
        _rodar(self.em_thread, lambda: testar_conexao(pedido, self.transporte), self._sinais, self._fim_teste)

    def _fim_teste(self, texto, erro):
        self.btn_testar.setEnabled(True)
        self.status.setText(f"Funcionou: a IA respondeu “{texto}”." if erro is None else str(erro))


# ---------------------------------------------------------------- chat
class CartaoPlano(QFrame):
    """Mostra o que a IA propôs, com Aplicar e Descartar; depois de aplicar, vira Desfazer."""
    aplicar = Signal(object)
    desfazer = Signal(object)

    def __init__(self, plano: ass.Plano):
        super().__init__()
        self.plano, self.lote = plano, None
        self.setObjectName("cartaoPlano")
        pal = tema.atual
        self.setStyleSheet(f"#cartaoPlano {{ border: 1px solid {pal.destaque}; border-radius: 10px; }}")
        lay = QVBoxLayout(self)
        self.titulo = QLabel(f"<b>Proposta ({len(plano.acoes)} mudança{'s' if len(plano.acoes) != 1 else ''})</b>")
        lay.addWidget(self.titulo)
        for a in plano.acoes:
            r = QLabel("• " + a.resumo)
            r.setWordWrap(True)
            r.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lay.addWidget(r)
        self.resultado = QLabel("")
        self.resultado.setWordWrap(True)
        self.resultado.hide()
        lay.addWidget(self.resultado)
        linha = QHBoxLayout()
        self.btn_aplicar = QPushButton("Aplicar tudo")
        self.btn_aplicar.setObjectName("primario")
        self.btn_descartar = QPushButton("Descartar")
        self.btn_desfazer = QPushButton("Desfazer")
        self.btn_desfazer.hide()
        for b in (self.btn_aplicar, self.btn_descartar, self.btn_desfazer):
            linha.addWidget(b)
        linha.addStretch(1)
        lay.addLayout(linha)
        self.btn_aplicar.clicked.connect(lambda: self.aplicar.emit(self))
        self.btn_descartar.clicked.connect(self._descartar)
        self.btn_desfazer.clicked.connect(lambda: self.desfazer.emit(self))

    def _descartar(self):
        self.btn_aplicar.hide()
        self.btn_descartar.hide()
        self.resultado.setText("Descartado. Nada foi mudado.")
        self.resultado.show()

    def mostrar_aplicado(self, lote: ass.Lote):
        self.lote = lote
        self.btn_aplicar.hide()
        self.btn_descartar.hide()
        txt = f"Aplicado: {lote.total} mudança(s)."
        if lote.erros:
            txt += "\nNão deu para fazer:\n" + "\n".join("• " + e for e in lote.erros)
        self.resultado.setText(txt)
        self.resultado.show()
        self.btn_desfazer.setVisible(lote.total > 0)

    def mostrar_desfeito(self):
        self.btn_desfazer.hide()
        self.resultado.setText("Desfeito. Tudo voltou como estava.")


class _Entrada(QPlainTextEdit):
    """Enter envia; Shift+Enter quebra a linha. Colar imagem ou arquivo vira anexo."""
    enviar = Signal()
    colou = Signal(object)          # lista de caminhos (str) ou uma QImage

    def canInsertFromMimeData(self, fonte):  # noqa: N802
        return fonte.hasImage() or fonte.hasUrls() or super().canInsertFromMimeData(fonte)

    def insertFromMimeData(self, fonte):  # noqa: N802
        if fonte.hasImage() and not fonte.hasText():
            self.colou.emit(fonte.imageData())
            return
        urls = [u.toLocalFile() for u in fonte.urls() if u.isLocalFile()] if fonte.hasUrls() else []
        if urls:
            self.colou.emit(urls)
            return
        super().insertFromMimeData(fonte)

    def keyPressEvent(self, e: QKeyEvent):  # noqa: N802
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            self.enviar.emit()
            return
        super().keyPressEvent(e)


def _imagem_para_png(img: QImage) -> bytes:
    dados = QByteArray()
    buf = QBuffer(dados)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(dados)


def reduzir_imagem(anexo: Anexo) -> Anexo:
    """Imagens muito grandes (fotos, telas em 4K) são reduzidas: a IA não precisa de mais que isso e o envio fica rápido."""
    if anexo.tipo != "imagem" or anexo.mime == "image/gif":
        return anexo
    img = QImage.fromData(anexo.dados)
    if img.isNull():
        return anexo
    if max(img.width(), img.height()) <= LADO_MAX_IMAGEM and len(anexo.dados) <= BYTES_REDUZIR:
        return anexo
    if max(img.width(), img.height()) > LADO_MAX_IMAGEM:
        img = img.scaled(LADO_MAX_IMAGEM, LADO_MAX_IMAGEM, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    novo = _imagem_para_png(img)
    if len(novo) >= len(anexo.dados) and max(img.width(), img.height()) <= LADO_MAX_IMAGEM:
        return anexo
    return Anexo(Path(anexo.nome).stem + ".png", "image/png", dados=novo)


def _miniatura(dados: bytes, lado: int) -> QPixmap | None:
    pm = QPixmap()
    if not pm.loadFromData(dados):
        return None
    return pm.scaled(lado, lado, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class ChipAnexo(QFrame):
    """Um arquivo esperando para ir na próxima mensagem: miniatura (se for imagem), nome e botão de remover."""
    remover = Signal(object)

    def __init__(self, anexo: Anexo):
        super().__init__()
        self.anexo = anexo
        self.setObjectName("chipAnexo")
        pal = tema.atual
        self.setStyleSheet(f"#chipAnexo {{ background:{pal.campo}; border:1px solid {pal.borda}; border-radius:8px; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 4, 4)
        self.miniatura = QLabel()
        pm = _miniatura(anexo.dados, 36) if anexo.tipo == "imagem" else None
        if pm is not None:
            self.miniatura.setPixmap(pm)
        else:
            self.miniatura.setPixmap(icones.pixmap("clipe", pal.texto, 18))
        lay.addWidget(self.miniatura)
        nome = anexo.nome if len(anexo.nome) <= 26 else anexo.nome[:23] + "..."
        self.rotulo = QLabel(nome)
        self.rotulo.setToolTip(anexo.nome)
        lay.addWidget(self.rotulo)
        self.btn_remover = QPushButton()
        self.btn_remover.setIcon(icones.icone("fechar", pal.texto, 14))
        self.btn_remover.setFlat(True)
        self.btn_remover.setFixedSize(22, 22)
        self.btn_remover.setToolTip("Remover")
        self.btn_remover.clicked.connect(lambda: self.remover.emit(self.anexo))
        lay.addWidget(self.btn_remover)


class PaginaIA(QWidget):
    def __init__(self, janela, transporte=transporte_http, em_thread: bool = True,
                 transporte_arquivo=transporte_multipart, fonte_audio=FonteQt):
        super().__init__()
        self.janela, self.servico = janela, janela.servico
        self.transporte, self.em_thread = transporte, em_thread
        self.transporte_arquivo = transporte_arquivo
        self.anexos: list[Anexo] = []
        self.transcrevendo = False
        self.gravador = Gravador(fonte_audio)
        self._sinais_voz = _Sinais()
        self._sinais_voz.pronto.connect(self._fim_transcricao)
        self.setAcceptDrops(True)
        self.historico: list[dict] = []
        self.conversa_id: int | None = None
        self.ocupado = False
        self.cartoes: list[CartaoPlano] = []
        self._sinais = _Sinais()
        self._sinais.pronto.connect(self._fim_turno)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(24, 16, 24, 16)
        topo = QHBoxLayout()
        self.titulo = QLabel("")
        topo.addWidget(self.titulo, 1)
        self.btn_nova = QPushButton("Nova conversa")
        self.btn_historico = QPushButton("Histórico")
        self.btn_config = QPushButton("Configurar IA")
        for b in (self.btn_nova, self.btn_historico, self.btn_config):
            topo.addWidget(b)
        raiz.addLayout(topo)

        self.pilha = QStackedWidget()
        raiz.addWidget(self.pilha, 1)

        # página 0: ainda sem chave
        vazio = QWidget()
        lv = QVBoxLayout(vazio)
        lv.addStretch(1)
        msg = QLabel("<b>Seu assistente de organização</b><br><br>Ele lê suas tarefas e sua agenda, sugere um "
                     "plano e só muda algo depois que você confirmar. Para começar, escolha uma IA e cole a "
                     "sua chave de API.")
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignCenter)
        lv.addWidget(msg)
        self.btn_comecar = QPushButton("Escolher a IA e colar a chave")
        self.btn_comecar.setObjectName("primario")
        lv.addWidget(self.btn_comecar, 0, Qt.AlignHCenter)
        lv.addStretch(1)
        self.pilha.addWidget(vazio)

        # página 1: chat
        chat = QWidget()
        lc = QVBoxLayout(chat)
        lc.setContentsMargins(0, 0, 0, 0)
        self.rolagem = QScrollArea()
        self.rolagem.setWidgetResizable(True)
        self.rolagem.setFrameShape(QFrame.NoFrame)
        self.corpo = QWidget()
        self.lay_msgs = QVBoxLayout(self.corpo)
        self.lay_msgs.setAlignment(Qt.AlignTop)
        self.rolagem.setWidget(self.corpo)
        self.rolagem.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        lc.addWidget(self.rolagem, 1)
        self.sugestoes = QWidget()
        ls = QHBoxLayout(self.sugestoes)
        ls.setContentsMargins(0, 0, 0, 0)
        self.chips: list[QPushButton] = []
        for rotulo, pedido in SUGESTOES:
            b = QPushButton(rotulo)
            b.clicked.connect(lambda _=False, p=pedido: self.enviar(p))
            ls.addWidget(b)
            self.chips.append(b)
        ls.addStretch(1)
        lc.addWidget(self.sugestoes)
        self.status = QLabel("")
        self.status.setObjectName("mensagemVazia")
        lc.addWidget(self.status)
        self.barra_anexos = QWidget()
        self.lay_anexos = QHBoxLayout(self.barra_anexos)
        self.lay_anexos.setContentsMargins(0, 0, 0, 0)
        self.lay_anexos.setAlignment(Qt.AlignLeft)
        self.barra_anexos.hide()
        lc.addWidget(self.barra_anexos)
        self.barra_gravacao = BarraGravacao()
        self.barra_gravacao.hide()
        lc.addWidget(self.barra_gravacao)
        self.linha_entrada = QWidget()
        linha = QHBoxLayout(self.linha_entrada)
        linha.setContentsMargins(0, 0, 0, 0)
        self.entrada = _Entrada()
        self.entrada.setObjectName("campoIA")
        self.entrada.setPlaceholderText("Peça algo, ou anexe uma imagem ou arquivo para a IA ler...")
        self.entrada.setFixedHeight(64)
        pal = tema.atual
        self.btn_anexar = QPushButton()
        self.btn_anexar.setIcon(icones.icone("clipe", pal.texto, 20))
        self.btn_anexar.setToolTip("Anexar imagem, PDF, Word ou texto (também dá para arrastar ou colar)")
        self.btn_voz = QPushButton()
        self.btn_voz.setIcon(icones.icone("microfone", pal.texto, 20))
        self.btn_voz.setToolTip("Falar em vez de digitar")
        self.btn_enviar = QPushButton("Enviar")
        self.btn_enviar.setObjectName("primario")
        linha.addWidget(self.btn_anexar, 0, Qt.AlignBottom)
        linha.addWidget(self.entrada, 1)
        linha.addWidget(self.btn_voz, 0, Qt.AlignBottom)
        linha.addWidget(self.btn_enviar, 0, Qt.AlignBottom)
        lc.addWidget(self.linha_entrada)
        self.pilha.addWidget(chat)

        self.btn_nova.clicked.connect(self.nova_conversa)
        self.btn_historico.clicked.connect(self._menu_historico)
        self.btn_config.clicked.connect(self.configurar)
        self.btn_comecar.clicked.connect(self.configurar)
        self.btn_enviar.clicked.connect(lambda: self.enviar())
        self.entrada.enviar.connect(lambda: self.enviar())
        self.entrada.colou.connect(self._colou)
        self.btn_anexar.clicked.connect(self.escolher_arquivos)
        self.btn_voz.clicked.connect(self.alternar_voz)
        self.barra_gravacao.confirmar.connect(self.terminar_gravacao)
        self.barra_gravacao.cancelar.connect(self.cancelar_gravacao)
        self.gravador.nivel.connect(self.barra_gravacao.onda.definir_nivel)
        self.gravador.tempo.connect(self.barra_gravacao.definir_tempo)
        self.gravador.erro.connect(self._erro_gravacao)
        self.gravador.limite.connect(self.terminar_gravacao)
        self.atualizar_estado()

    # ---- estado
    def atualizar_estado(self):
        cfg = self.servico.ia
        p = PROVEDORES[cfg.ativo]
        self.titulo.setText(f"<b>Assistente</b>  ·  {p.rotulo}  ·  {cfg.modelo()}")
        self.pilha.setCurrentIndex(1 if cfg.tem_chave() else 0)
        self.sugestoes.setVisible(not self.historico)

    def configurar(self):
        DialogoIA(self, self.servico, self.transporte, self.em_thread).exec()
        self.atualizar_estado()

    # ---- bolhas
    def _bolha(self, papel: str, texto: str, erro: bool = False) -> QLabel:
        pal = tema.atual
        b = QLabel(texto)
        b.setWordWrap(True)
        b.setTextInteractionFlags(Qt.TextSelectableByMouse)
        if papel == "assistente" and not erro:
            b.setTextFormat(Qt.MarkdownText)
        fundo = pal.linha_selecionada if papel == "usuario" else pal.campo
        cor = pal.vermelho if erro else pal.texto
        b.setStyleSheet(f"background:{fundo}; color:{cor}; border-radius:10px; padding:10px 12px;")
        b.setMaximumWidth(720)
        b.setObjectName("bolha_" + papel)
        linha = QWidget()
        lh = QHBoxLayout(linha)
        lh.setContentsMargins(0, 0, 0, 0)
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        if papel == "usuario":
            lh.addStretch(1)
            lh.addWidget(b, 4)
        else:
            lh.addWidget(b, 4)
            lh.addStretch(1)
        self.lay_msgs.addWidget(linha)
        QTimer.singleShot(0, lambda: self.rolagem.verticalScrollBar().setValue(self.rolagem.verticalScrollBar().maximum()))
        return b

    def _bolha_anexos(self, anexos: list[dict]) -> QWidget | None:
        """Miniaturas das imagens (enquanto a conversa está aberta) e nomes dos demais arquivos, alinhados à direita."""
        if not anexos:
            return None
        pal = tema.atual
        linha = QWidget()
        linha.setObjectName("linhaAnexos")
        lh = QHBoxLayout(linha)
        lh.setContentsMargins(0, 0, 0, 0)
        lh.addStretch(1)
        for a in anexos:
            r = QLabel()
            pm = _miniatura(base64.b64decode(a["b64"]), 140) if a.get("tipo") == "imagem" and a.get("b64") else None
            if pm is not None:
                r.setPixmap(pm)
                r.setToolTip(a["nome"])
            else:
                r.setText(("Imagem: " if a.get("tipo") == "imagem" else "Arquivo: ") + a["nome"])
            r.setObjectName("anexoNaConversa")
            r.setStyleSheet(f"background:{pal.linha_selecionada}; color:{pal.texto}; border-radius:8px; padding:6px;")
            lh.addWidget(r)
        self.lay_msgs.addWidget(linha)
        return linha

    def _limpar_chat(self):
        while self.lay_msgs.count():
            w = self.lay_msgs.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.cartoes.clear()

    def _redesenhar(self):
        self._limpar_chat()
        for m in self.historico:
            if m["papel"] == "usuario":
                self._bolha_anexos(m.get("anexos") or [])
                if m.get("texto"):
                    self._bolha("usuario", m["texto"])
            elif m["papel"] == "assistente" and m.get("texto"):
                self._bolha("assistente", m["texto"])

    # ---- conversas
    def nova_conversa(self):
        if self.ocupado:
            return
        self.historico, self.conversa_id = [], None
        self._limpar_chat()
        self.status.setText("")
        self.atualizar_estado()

    def _menu_historico(self):
        menu = QMenu(self)
        conversas = self.servico.conversas_ia.listar()
        if not conversas:
            menu.addAction("Nenhuma conversa ainda").setEnabled(False)
        for c in conversas:
            menu.addAction(c["titulo"], lambda i=c["id"]: self.abrir_conversa(i))
        if conversas:
            menu.addSeparator()
            menu.addAction("Apagar todas", self._apagar_conversas)
        menu.exec(self.btn_historico.mapToGlobal(self.btn_historico.rect().bottomLeft()))

    def abrir_conversa(self, conversa_id: int):
        if self.ocupado:
            return
        self.historico, self.conversa_id = self.servico.conversas_ia.carregar(conversa_id), conversa_id
        self._redesenhar()
        self.atualizar_estado()

    def _apagar_conversas(self):
        for c in self.servico.conversas_ia.listar(500):
            self.servico.conversas_ia.apagar(c["id"])
        self.nova_conversa()

    # ---- anexos
    def escolher_arquivos(self):
        filtro = "Arquivos que a IA lê (*.png *.jpg *.jpeg *.webp *.gif *.pdf *.docx *.txt *.md *.csv *.json *.ics);;Todos (*)"
        caminhos, _ = QFileDialog.getOpenFileNames(self, "Anexar arquivos", "", filtro)
        if caminhos:
            self.adicionar_arquivos(caminhos)

    def adicionar_arquivos(self, caminhos) -> int:
        """Lê os arquivos e os deixa prontos para a próxima mensagem. Devolve quantos entraram."""
        entraram = 0
        for c in caminhos:
            try:
                self.adicionar_anexo(carregar_arquivo(c))
                entraram += 1
            except ErroIA as e:
                self.status.setText(str(e))
        return entraram

    def adicionar_anexo(self, anexo: Anexo) -> None:
        if len(self.anexos) >= MAX_ANEXOS:
            raise ErroIA(f"Dá para anexar até {MAX_ANEXOS} arquivos por mensagem.")
        prov = PROVEDORES[self.servico.ia.ativo]
        if anexo.tipo == "imagem" and not prov.le_imagem:
            raise ErroIA(f"{prov.rotulo} não lê imagens. Troque para Gemini, Claude ou ChatGPT em Configurar IA.")
        self.anexos.append(reduzir_imagem(anexo))
        self._mostrar_anexos()
        self.status.setText("")

    def remover_anexo(self, anexo: Anexo) -> None:
        if anexo in self.anexos:
            self.anexos.remove(anexo)
        self._mostrar_anexos()

    def _mostrar_anexos(self) -> None:
        while self.lay_anexos.count():
            w = self.lay_anexos.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        for a in self.anexos:
            chip = ChipAnexo(a)
            chip.remover.connect(self.remover_anexo)
            self.lay_anexos.addWidget(chip)
        self.barra_anexos.setVisible(bool(self.anexos))

    def _colou(self, conteudo) -> None:
        try:
            if isinstance(conteudo, QImage):
                n = sum(1 for a in self.anexos if a.nome.startswith("imagem-colada")) + 1
                self.adicionar_anexo(reduzir_imagem(carregar_bytes(f"imagem-colada-{n}.png", _imagem_para_png(conteudo))))
            else:
                self.adicionar_arquivos(conteudo)
        except ErroIA as e:
            self.status.setText(str(e))

    def dragEnterEvent(self, e):  # noqa: N802
        if self.pilha.currentIndex() == 1 and e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        caminhos = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if caminhos:
            e.acceptProposedAction()
            self.adicionar_arquivos(caminhos)

    # ---- voz
    def alternar_voz(self):
        if self.gravador.gravando:
            self.terminar_gravacao()
        else:
            self.comecar_gravacao()

    def comecar_gravacao(self) -> bool:
        if self.ocupado or self.transcrevendo or self.gravador.gravando:
            return False
        if self.servico.ia.provedor_voz() is None:
            prov = PROVEDORES[self.servico.ia.ativo]
            self.status.setText(f"{prov.rotulo} não transcreve voz. Em Configurar IA, na seção de voz, escolha "
                                "Gemini, ChatGPT ou Groq, ou use o ditado do Windows (tecla Windows + H) na caixa "
                                "de texto.")
            return False
        try:
            self.gravador.iniciar()
        except ErroIA as e:
            self.status.setText(str(e))
            return False
        except Exception as e:  # noqa: BLE001 - driver de áudio, QtMultimedia ausente etc.
            self.status.setText(f"Não consegui usar o microfone: {e}")
            return False
        nome = getattr(self.gravador._fonte, "nome", "")
        self.status.setText(f"Gravando com: {nome}" if nome else "")
        self.linha_entrada.hide()
        self.barra_gravacao.comecar()
        return True

    def _fechar_barra_voz(self):
        self.barra_gravacao.encerrar()
        self.linha_entrada.show()

    def cancelar_gravacao(self):
        self.gravador.cancelar()
        self._fechar_barra_voz()

    def _erro_gravacao(self, msg: str):
        self._fechar_barra_voz()
        self.status.setText(msg)

    def terminar_gravacao(self):
        if not self.gravador.gravando:
            return
        pcm = self.gravador.parar()
        self._fechar_barra_voz()
        if len(pcm) < 3200:                          # menos de 0,1 s: foi um clique sem querer
            self.status.setText("Não ouvi nada. Tente de novo.")
            return
        wav = wav_de_pcm16(pcm)
        pedido = self.servico.ia.pedido(self.servico.ia.provedor_voz())
        self.transcrevendo = True
        self.btn_voz.setEnabled(False)
        self.status.setText("Transcrevendo o que você falou...")
        _rodar(self.em_thread, lambda: transcrever(pedido, wav, self.transporte, self.transporte_arquivo),
               self._sinais_voz, self._fim_transcricao)

    def _fim_transcricao(self, texto, erro):
        self.transcrevendo = False
        self.btn_voz.setEnabled(True)
        if erro is not None:
            self.status.setText(str(erro) if isinstance(erro, ErroIA) else f"Não consegui transcrever: {erro}")
            return
        if not texto:
            self.status.setText("Não entendi nada no áudio. Tente de novo.")
            return
        atual = self.entrada.toPlainText().rstrip()
        self.entrada.setPlainText((atual + " " if atual else "") + texto)
        self.entrada.moveCursor(self.entrada.textCursor().MoveOperation.End)
        self.entrada.setFocus()
        self.status.setText("Revise o texto e envie.")

    # ---- envio
    def enviar(self, texto: str | None = None):
        texto = (texto if texto is not None else self.entrada.toPlainText()).strip()
        anexos_pendentes = list(self.anexos)
        if (not texto and not anexos_pendentes) or self.ocupado:
            return
        if not self.servico.ia.tem_chave():
            self.atualizar_estado()
            return
        if self.gravador.gravando:
            return
        try:
            anexos = preparar_anexos(self.servico.ia.ativo, anexos_pendentes)
        except ErroIA as e:
            self.status.setText(str(e))
            return
        if self.janela.detalhe.tarefa is not None:
            self.janela.detalhe._salvar()               # o que está sendo digitado entra no que a IA vê
        self.entrada.clear()
        self.anexos = []
        self._mostrar_anexos()
        self._bolha_anexos(anexos)
        if texto:
            self._bolha("usuario", texto)
        self.sugestoes.hide()
        self.ocupado = True
        self.btn_enviar.setEnabled(False)
        self.status.setText("Pensando...")
        pedido = self.servico.ia.pedido()
        hist = list(self.historico)
        banco = self.servico.banco
        if banco.caminho == ":memory:" or not self.em_thread:
            funcao = lambda: ass.Assistente(self.servico, pedido, self.transporte).turno(hist, texto, anexos)   # noqa: E731
        else:
            pasta, caminho = self.servico.pasta_dados, banco.caminho
            funcao = lambda: ass.turno_em_arquivo(caminho, pasta, pedido, hist, texto, self.transporte, anexos)  # noqa: E731
        _rodar(self.em_thread and banco.caminho != ":memory:", funcao, self._sinais, self._fim_turno)

    def _fim_turno(self, turno, erro):
        self.ocupado = False
        self.btn_enviar.setEnabled(True)
        self.status.setText("")
        if erro is not None:
            self._bolha("assistente", str(erro) if isinstance(erro, ErroIA) else f"Algo deu errado: {erro}", erro=True)
            return
        self.historico = turno.historico
        if turno.texto:
            self._bolha("assistente", turno.texto)
        if turno.plano:
            cartao = CartaoPlano(turno.plano)
            cartao.aplicar.connect(self._aplicar)
            cartao.desfazer.connect(self._desfazer)
            self.cartoes.append(cartao)
            self.lay_msgs.addWidget(cartao)
            QTimer.singleShot(0, lambda: self.rolagem.verticalScrollBar().setValue(self.rolagem.verticalScrollBar().maximum()))
        self.conversa_id = self.servico.conversas_ia.salvar(self.conversa_id, self.historico)
        self.atualizar_estado()

    # ---- aplicar e desfazer
    def _aplicar(self, cartao: CartaoPlano):
        lote = ass.aplicar_plano(self.servico, cartao.plano, self.servico.ia)
        cartao.mostrar_aplicado(lote)
        self.janela.pedir_atualizacao()
        self.atualizar_estado()

    def _desfazer(self, cartao: CartaoPlano):
        if cartao.lote is not None:
            ass.desfazer_lote(self.servico, cartao.lote, self.servico.ia)
            cartao.mostrar_desfeito()
            self.janela.pedir_atualizacao()
