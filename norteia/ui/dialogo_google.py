"""Integrações: grade de serviços e a tela "Integrar o Google Calendar".

Só o Google Calendar funciona por enquanto; os outros cartões aparecem como "Em breve". O login e a sincronização
rodam fora da thread da tela (`GerenteGoogle`), e o banco da tela só é tocado na thread principal.
"""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPalette, QPixmap
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from ..core import google_agenda as ga
from . import tema

URL_CONSOLE = "https://console.cloud.google.com/"

AJUDA_CREDENCIAIS = (
    "<b>Como obter o Client ID e o Client secret (uma vez só, uns 5 minutos):</b><ol>"
    f"<li>Abra o <a href='{URL_CONSOLE}'><span style='color:#6ab7ff'>Google Cloud Console</span></a> com a sua conta e crie um projeto (ex.: “Norteia”).</li>"
    "<li>Em <i>APIs e serviços › Biblioteca</i>, procure <b>Google Calendar API</b> e clique em <b>Ativar</b>.</li>"
    "<li>Em <i>Tela de permissão OAuth</i>, escolha <b>Externo</b>, preencha o nome do app e o seu e-mail. Depois "
    "clique em <b>Publicar app</b> (status “Em produção”). Sem isso o login vence a cada 7 dias.</li>"
    "<li>Em <i>Credenciais › Criar credenciais › ID do cliente OAuth</i>, tipo <b>App para computador</b>.</li>"
    "<li>Copie o <b>ID do cliente</b> e a <b>Chave secreta do cliente</b> para os campos acima.</li></ol>"
    "Na primeira vez o Google avisa “app não verificado”: clique em <i>Avançado › Acessar (não seguro)</i>. É o "
    "seu próprio app, e o acesso fica só no seu computador. Há um passo a passo completo no arquivo "
    "<b>docs/GUIA_GOOGLE_CALENDAR.md</b>.")


# ---------------------------------------------------------------- trabalho em segundo plano
class _Sinais(QObject):
    sincronizou = Signal(object, object)    # (Resumo | None, erro | None)
    entrou = Signal(object, object)         # (dados do login | None, erro | None)


class _Trabalho(QRunnable):
    def __init__(self, funcao, sinal):
        super().__init__()
        self.funcao, self.sinal = funcao, sinal

    def run(self):
        try:
            self.sinal.emit(self.funcao(), None)
        except Exception as e:  # noqa: BLE001 - qualquer falha vira mensagem na tela
            self.sinal.emit(None, e)


class GerenteGoogle(QObject):
    """Dono do login e da sincronização do Google. Uma instância por janela."""

    terminou = Signal(object)      # Resumo (erro em .erro quando falhou)
    mudou_estado = Signal()        # conectou, desconectou, começou/terminou de sincronizar

    def __init__(self, servico, em_thread: bool = True, transporte=ga.transporte_padrao, abrir=None):
        super().__init__()
        self.servico, self.em_thread, self.transporte = servico, em_thread, transporte
        self.abrir = abrir
        self.sincronizando = False
        self.entrando = False
        self._sinais = _Sinais()
        self._sinais.sincronizou.connect(self._fim_sync)
        self._sinais.entrou.connect(self._fim_login)

    @property
    def google(self) -> ga.Google:
        return self.servico.google

    # ---- login
    def entrar(self) -> None:
        g = self.google
        if not g.configurado:
            self._fim_login(None, ga.ErroGoogle("Informe o Client ID e o Client secret primeiro."))
            return
        self.entrando = True
        self.mudou_estado.emit()
        cid, segredo = g.cliente.client_id, g.cliente.client_secret
        kw = {"abrir": self.abrir} if self.abrir else {}

        def tarefa():
            return ga.login_pelo_navegador(cid, segredo, transporte=self.transporte, **kw)

        self._rodar(tarefa, self._sinais.entrou, self._fim_login)

    def _fim_login(self, dados, erro):
        self.entrando = False
        if erro is None and dados:
            self.google.cliente.guardar_login(dados)
            self.mudou_estado.emit()
            self.sincronizar()
            return
        self.mudou_estado.emit()
        self.terminou.emit(ga.Resumo(erro=str(erro) if erro else "Login cancelado."))

    # ---- sincronização
    def sincronizar(self) -> None:
        if self.sincronizando or not self.google.conectado:
            return
        self.sincronizando = True
        self.mudou_estado.emit()
        caminho = self.servico.banco.caminho
        pasta = self.servico.pasta_dados
        if caminho == ":memory:" or not self.em_thread:
            # banco em memória não é visível a outra conexão: roda aqui mesmo
            try:
                self._fim_sync(self.google.sincronizar(), None)
            except Exception as e:  # noqa: BLE001
                self._fim_sync(None, e)
            return
        self._rodar(lambda: ga.sincronizar_arquivo(caminho, pasta, self.transporte), self._sinais.sincronizou,
                    self._fim_sync)

    def _fim_sync(self, resumo, erro):
        self.sincronizando = False
        if resumo is None:
            resumo = ga.Resumo(erro=str(erro) if erro else "Falha desconhecida.")
        self.mudou_estado.emit()
        self.terminou.emit(resumo)

    def _rodar(self, funcao, sinal, direto):
        if self.em_thread:
            QThreadPool.globalInstance().start(_Trabalho(funcao, sinal))
        else:
            try:
                direto(funcao(), None)
            except Exception as e:  # noqa: BLE001
                direto(None, e)

    # ---- texto de estado
    def resumo_texto(self) -> str:
        g = self.google
        if self.entrando:
            return "Aguardando você autorizar no navegador..."
        if self.sincronizando:
            return "Sincronizando..."
        erro = self.servico.banco.meta("google_ultimo_erro", "") or ""
        if erro:
            return f"Problema na última sincronização: {erro}"
        quando = self.servico.banco.meta("google_ultima_sync", "") or ""
        if not quando:
            return "Ainda não sincronizado."
        try:
            hora = datetime.fromisoformat(quando).astimezone().strftime("%d/%m %H:%M")
        except ValueError:
            hora = quando[:16]
        return f"Última sincronização: {hora}." + ("" if g.conectado else " (desconectado)")


# ---------------------------------------------------------------- tela do Google
def _bolinha(cor: str) -> QIcon:
    pm = QPixmap(14, 14)
    pm.fill(QColor(cor))
    return QIcon(pm)


class DialogoGoogle(QDialog):
    """Integrar o Google Calendar."""

    def __init__(self, parent, servico, gerente: GerenteGoogle):
        super().__init__(parent)
        self.servico, self.gerente = servico, gerente
        self.mudou = False
        self.setWindowTitle("Integrar o Google Calendar")
        self.setMinimumSize(620, 560)
        lay = QVBoxLayout(self)
        self.paginas = QStackedWidget()
        lay.addWidget(self.paginas, 1)
        self.status = QLabel("")
        self.status.setObjectName("mensagemVazia")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.accept)
        linha = QHBoxLayout()
        linha.addStretch(1)
        linha.addWidget(fechar)
        lay.addLayout(linha)
        self._montar_entrada()
        self._montar_conectado()
        gerente.mudou_estado.connect(self._atualizar)
        gerente.terminou.connect(self._terminou)
        self._atualizar()

    # ---- página 1: ainda não conectado
    def _montar_entrada(self):
        pg = QWidget()
        lay = QVBoxLayout(pg)
        for texto in ("<b>Veja seus eventos do Google no calendário e leve suas tarefas para lá.</b>",
                      "O login é feito no navegador, direto com o Google. A autorização fica guardada só "
                      "neste computador."):
            rotulo = QLabel(texto)
            rotulo.setWordWrap(True)
            lay.addWidget(rotulo)
        lay.addWidget(QLabel("ID do cliente (Client ID)"))
        self.campo_id = QLineEdit(self.gerente.google.cliente.client_id)
        self.campo_id.setPlaceholderText("xxxxxxxx.apps.googleusercontent.com")
        lay.addWidget(self.campo_id)
        lay.addWidget(QLabel("Chave secreta do cliente (Client secret)"))
        self.campo_segredo = QLineEdit(self.gerente.google.cliente.client_secret)
        self.campo_segredo.setEchoMode(QLineEdit.Password)
        lay.addWidget(self.campo_segredo)
        self.btn_conectar = QPushButton("Conectar com o Google")
        self.btn_conectar.setObjectName("primario")
        self.btn_conectar.clicked.connect(self.conectar)
        lay.addWidget(self.btn_conectar)
        ajuda = QLabel(AJUDA_CREDENCIAIS)
        ajuda.setWordWrap(True)
        ajuda.setTextFormat(Qt.RichText)
        pal = ajuda.palette()
        pal.setColor(QPalette.Link, QColor(tema.atual.destaque))
        ajuda.setPalette(pal)
        ajuda.setOpenExternalLinks(False)
        ajuda.linkActivated.connect(lambda u: QDesktopServices.openUrl(QUrl(u)))
        lay.addWidget(ajuda)
        lay.addStretch(1)
        self.paginas.addWidget(pg)

    # ---- página 2: conectado
    def _montar_conectado(self):
        pg = QWidget()
        lay = QVBoxLayout(pg)
        self.titulo_conta = QLabel("")
        lay.addWidget(self.titulo_conta)
        lay.addWidget(QLabel("Calendários que aparecem no app (somente leitura):"))
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.NoFrame)
        rolagem.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        corpo = QWidget()
        self.lay_calendarios = QVBoxLayout(corpo)
        self.lay_calendarios.setAlignment(Qt.AlignTop)
        rolagem.setWidget(corpo)
        self.caixas: dict[str, QCheckBox] = {}
        lay.addWidget(rolagem, 1)
        self.chk_enviar = QCheckBox("Enviar minhas tarefas com data para o Google Calendar (calendário “Tarefas”)")
        self.chk_enviar.toggled.connect(self._alternou_enviar)
        lay.addWidget(self.chk_enviar)
        dica = QLabel("As tarefas sem hora viram eventos de dia inteiro. Se você mudar o horário do evento no "
                      "Google, a tarefa muda aqui (vale a edição mais recente).")
        dica.setWordWrap(True)
        dica.setObjectName("mensagemVazia")
        lay.addWidget(dica)
        linha = QHBoxLayout()
        self.btn_sync = QPushButton("Sincronizar agora")
        self.btn_sync.clicked.connect(self.gerente.sincronizar)
        self.btn_reentrar = QPushButton("Entrar de novo")
        self.btn_reentrar.setToolTip("Refaz o login no navegador (use se o Google pedir autorização outra vez)")
        self.btn_reentrar.clicked.connect(self.gerente.entrar)
        self.btn_sair = QPushButton("Desconectar")
        self.btn_sair.clicked.connect(self.desconectar)
        linha.addWidget(self.btn_sync)
        linha.addWidget(self.btn_reentrar)
        linha.addWidget(self.btn_sair)
        linha.addStretch(1)
        lay.addLayout(linha)
        self.paginas.addWidget(pg)

    # ---- ações
    def conectar(self):
        g = self.gerente.google
        g.cliente.definir_credenciais(self.campo_id.text(), self.campo_segredo.text())
        if not g.configurado:
            self.status.setText("Preencha o Client ID e o Client secret (veja “Como obter” abaixo).")
            return
        self.status.setText("Abrindo o navegador para você autorizar...")
        self.gerente.entrar()

    def desconectar(self):
        self.gerente.google.sair(apagar_eventos=True)
        self.mudou = True
        self.status.setText("Desconectado. Os eventos do Google saíram do calendário.")
        self._atualizar()

    def _marcou(self, ass_id: int, ligado: bool):
        if getattr(self, "_recarregando", False):
            return
        self.gerente.google.definir_calendario_ativo(ass_id, ligado)
        self.mudou = True
        if ligado:
            self.gerente.sincronizar()

    def _alternou_enviar(self, ligado: bool):
        if getattr(self, "_recarregando", False):
            return
        self.gerente.google.definir_enviar_tarefas(ligado)
        if ligado:
            self.gerente.sincronizar()

    def _terminou(self, resumo):
        if resumo.erro:
            self.status.setText(resumo.erro)
        else:
            partes = []
            if resumo.eventos_lidos:
                partes.append(f"{resumo.eventos_lidos} evento(s) lido(s)")
            if resumo.enviados or resumo.atualizados:
                partes.append(f"{resumo.enviados + resumo.atualizados} tarefa(s) enviada(s)")
            if resumo.importados:
                partes.append(f"{resumo.importados} nova(s) tarefa(s) vinda(s) do Google")
            if resumo.alteradas_no_google:
                partes.append(f"{resumo.alteradas_no_google} tarefa(s) atualizada(s) pelo Google")
            if resumo.avisos:
                partes.append("avisos: " + "; ".join(resumo.avisos))
            self.status.setText("Pronto. " + (", ".join(partes) + "." if partes else "Nada mudou."))
        self.mudou = True
        self._atualizar()

    # ---- estado
    def _atualizar(self):
        g = self.gerente.google
        conectado = g.conectado
        self.paginas.setCurrentIndex(1 if conectado else 0)
        self.btn_conectar.setEnabled(not self.gerente.entrando)
        if not conectado:
            return
        self._recarregando = True
        try:
            conta = g.conta
            self.titulo_conta.setText(f"<b>Conectado</b>{' como ' + conta if conta else ''}. "
                                      f"{self.gerente.resumo_texto()}")
            self.chk_enviar.setChecked(g.enviar_tarefas)
            while self.lay_calendarios.count():
                w = self.lay_calendarios.takeAt(0).widget()
                w.setParent(None)
                w.deleteLater()
            self.caixas.clear()
            for a in g.calendarios():
                if a["ref"] == self.servico.banco.meta("google_cal_tarefas", ""):
                    continue            # o calendário "Tarefas" é nosso, não aparece na lista
                cx = QCheckBox(a["nome"])
                cx.setIcon(_bolinha(a["cor"]))
                cx.setChecked(bool(a["ativa"]))
                cx.toggled.connect(lambda ligado, i=a["id"]: self._marcou(i, ligado))
                self.lay_calendarios.addWidget(cx)
                cx.show()
                self.caixas[a["nome"]] = cx
            self.btn_sync.setEnabled(not self.gerente.sincronizando)
        finally:
            self._recarregando = False


# ---------------------------------------------------------------- grade de integrações
_FUTURAS = [("Outlook", "#2a73cc"), ("Exchange", "#1b5fb0"), ("iCloud", "#9aa0a6"), ("CalDAV", "#6b5ce7"),
            ("Notion", "#e6e6e6"), ("Zapier", "#ff6a2b"), ("IFTTT", "#33ccff"), ("Gmail", "#ea4335"),
            ("Slack", "#4a154b"), ("Alexa", "#31c4f3")]


class _Cartao(QFrame):
    clicado = Signal()

    def __init__(self, nome: str, cor: str, subtitulo: str = "", ativo: bool = True):
        super().__init__()
        self.setObjectName("cartaoIntegracao")
        self.setCursor(Qt.PointingHandCursor if ativo else Qt.ArrowCursor)
        self.ativo = ativo
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignHCenter)
        sigla = QLabel(nome[:1].upper())
        sigla.setFixedSize(44, 44)
        sigla.setAlignment(Qt.AlignCenter)
        texto = "#101114" if QColor(cor).lightness() > 150 else "#ffffff"
        sigla.setStyleSheet(f"background:{cor}; color:{texto}; border-radius:10px; font-size:20px; font-weight:700;")
        lay.addWidget(sigla, 0, Qt.AlignHCenter)
        t = QLabel(nome)
        t.setAlignment(Qt.AlignCenter)
        t.setWordWrap(True)
        lay.addWidget(t)
        s = QLabel(subtitulo)
        s.setAlignment(Qt.AlignCenter)
        s.setObjectName("mensagemVazia")
        lay.addWidget(s)
        pal = tema.atual
        self.setStyleSheet(f"#cartaoIntegracao {{ border:1px solid {pal.borda}; border-radius:10px; }}"
                           + ("" if ativo else " QLabel { color: %s; }" % pal.apagado))
        self.setFixedSize(150, 130)

    def mousePressEvent(self, e):  # noqa: N802
        if self.ativo and e.button() == Qt.LeftButton:
            self.clicado.emit()


class DialogoIntegracoes(QDialog):
    def __init__(self, parent, abrir_google, abrir_url):
        super().__init__(parent)
        self.setWindowTitle("Integrações")
        self.setMinimumSize(740, 460)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<b>Calendários e serviços</b>"))
        grade = QGridLayout()
        grade.setSpacing(12)
        cartoes = [_Cartao("Google Calendar", "#4285f4", "Disponível"),
                   _Cartao("Calendário por link (URL)", "#4dd0b1", "Somente leitura")]
        cartoes[0].clicado.connect(lambda: (self.accept(), abrir_google()))
        cartoes[1].clicado.connect(lambda: (self.accept(), abrir_url()))
        cartoes += [_Cartao(n, c, "Em breve", ativo=False) for n, c in _FUTURAS]
        self.cartoes = cartoes
        for i, c in enumerate(cartoes):
            grade.addWidget(c, i // 4, i % 4)
        lay.addLayout(grade)
        lay.addStretch(1)
        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.reject)
        linha = QHBoxLayout()
        linha.addStretch(1)
        linha.addWidget(fechar)
        lay.addLayout(linha)
