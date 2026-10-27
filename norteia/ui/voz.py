"""Gravação de voz para o assistente: captura do microfone, onda animada e barra de gravação.

A captura fica atrás de uma "fonte" (`FonteQt` usa o microfone de verdade; os testes usam uma fonte falsa), então o resto
da tela não depende de ter um microfone.
"""
from __future__ import annotations

from collections import deque

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from ..core.arquivos_ia import ConversorPCM, nivel_do_pcm16
from ..core.ia import ErroIA
from . import tema

TAXA = 16000
BYTES_POR_SEGUNDO = TAXA * 2
MSG_SEM_MICROFONE = ("Não encontrei um microfone. Conecte um e tente de novo.")
MSG_PRIVACIDADE = ("Não estou recebendo som do microfone. No Windows, confira em Configurações > Privacidade e "
                   "segurança > Microfone se o acesso está liberado para aplicativos.")


class FonteQt:
    """Microfone padrão do computador, via QtMultimedia. Entrega PCM de 16 bits, 16 kHz, mono."""

    def __init__(self):
        self.audio = None
        self.io = None
        self._conv = None
        self._receber = None
        self.nome = ""

    def abrir(self, ao_receber) -> None:
        try:
            from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices, QtAudio  # noqa: PLC0415
        except ImportError as e:
            raise ErroIA("Esta instalação não tem suporte a áudio (QtMultimedia).") from e
        dispositivo = QMediaDevices.defaultAudioInput()
        if dispositivo.isNull():
            raise ErroIA(MSG_SEM_MICROFONE)
        try:
            self.nome = dispositivo.description()
        except Exception:  # noqa: BLE001
            self.nome = ""
        formato = QAudioFormat()
        formato.setSampleRate(TAXA)
        formato.setChannelCount(1)
        formato.setSampleFormat(QAudioFormat.Int16)
        if not dispositivo.isFormatSupported(formato):
            formato = dispositivo.preferredFormat()
        nomes = {QAudioFormat.Int16: "int16", QAudioFormat.Int32: "int32", QAudioFormat.Float: "float",
                 QAudioFormat.UInt8: "uint8"}
        nome = nomes.get(formato.sampleFormat())
        if nome is None:
            raise ErroIA("O microfone usa um formato de áudio que o aplicativo ainda não entende.")
        self._conv = ConversorPCM(formato.sampleRate(), formato.channelCount(), nome, TAXA)
        self._receber = ao_receber
        self.audio = QAudioSource(dispositivo, formato)
        self.io = self.audio.start()
        if self.io is None or self.audio.error() != QtAudio.Error.NoError:
            self.fechar()
            raise ErroIA(MSG_PRIVACIDADE)
        self.io.readyRead.connect(self._ler)

    def _ler(self):
        if self.io is None:
            return
        dados = bytes(self.io.readAll())
        if dados and self._receber:
            pcm = self._conv.converter(dados)
            if pcm:
                self._receber(pcm)

    def fechar(self) -> None:
        if self.audio is not None:
            try:
                self.audio.stop()
            except RuntimeError:
                pass
        self.audio, self.io, self._receber = None, None, None


class Gravador(QObject):
    """Grava até a pessoa parar (ou até o limite). Avisa o volume para a onda e o tempo decorrido."""
    nivel = Signal(float)
    tempo = Signal(float)
    erro = Signal(str)
    limite = Signal()

    def __init__(self, fabrica=FonteQt, limite_segundos: int = 180, espera_som_ms: int = 3000):
        super().__init__()
        self.fabrica, self.limite_segundos = fabrica, limite_segundos
        self._fonte = None
        self._pcm = bytearray()
        self._avisou_limite = False
        self._espera = QTimer(self)
        self._espera.setSingleShot(True)
        self._espera.setInterval(espera_som_ms)
        self._espera.timeout.connect(self._sem_som)

    @property
    def gravando(self) -> bool:
        return self._fonte is not None

    @property
    def segundos(self) -> float:
        return len(self._pcm) / BYTES_POR_SEGUNDO

    def iniciar(self) -> None:
        """Começa a gravar. Lança ErroIA com uma mensagem amigável se não der."""
        if self.gravando:
            return
        self._pcm = bytearray()
        self._avisou_limite = False
        fonte = self.fabrica()
        fonte.abrir(self.receber)            # pode lançar ErroIA
        self._fonte = fonte
        self._espera.start()

    def receber(self, pcm: bytes) -> None:
        if not self.gravando or not pcm:
            return
        self._espera.stop()
        self._pcm.extend(pcm)
        self.nivel.emit(nivel_do_pcm16(bytes(pcm[-3200:])))
        self.tempo.emit(self.segundos)
        if self.segundos >= self.limite_segundos and not self._avisou_limite:
            self._avisou_limite = True
            self.limite.emit()

    def _sem_som(self) -> None:
        if self.gravando and not self._pcm:
            self.cancelar()
            self.erro.emit(MSG_PRIVACIDADE)

    def _encerrar(self) -> None:
        self._espera.stop()
        fonte, self._fonte = self._fonte, None
        if fonte is not None:
            fonte.fechar()

    def parar(self) -> bytes:
        """Termina e devolve o áudio gravado (PCM 16 bits, 16 kHz, mono)."""
        self._encerrar()
        return bytes(self._pcm)

    def cancelar(self) -> None:
        self._encerrar()
        self._pcm = bytearray()


class OndaVoz(QWidget):
    """Barrinhas que sobem e descem com o volume da voz e vão correndo para a esquerda."""
    BARRAS = 240                 # memória; quantas aparecem depende da largura
    LARGURA_BARRA = 3
    ESPACO = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.valores = deque([0.0] * self.BARRAS, maxlen=self.BARRAS)
        self._alvo = 0.0
        self._suave = 0.0
        self.setMinimumSize(160, 40)
        self.setObjectName("ondaVoz")
        self._relogio = QTimer(self)
        self._relogio.setInterval(45)
        self._relogio.timeout.connect(self.passo)

    def definir_nivel(self, nivel: float) -> None:
        """Volume mais recente (0 a 1). Vozes normais ficam baixas, por isso a curva é realçada."""
        self._alvo = max(self._alvo, min(1.0, max(0.0, nivel)) ** 0.55)

    def passo(self) -> None:
        """Avanca uma barrinha: sobe depressa, desce devagar."""
        if self._alvo > self._suave:
            self._suave = self._suave * 0.3 + self._alvo * 0.7
        else:
            self._suave = self._suave * 0.65 + self._alvo * 0.35
        self.valores.append(self._suave)
        self._alvo *= 0.55
        self.update()

    def iniciar(self) -> None:
        self.limpar()
        self._relogio.start()

    def parar(self) -> None:
        self._relogio.stop()

    def limpar(self) -> None:
        self.valores.extend([0.0] * self.BARRAS)
        self._alvo = self._suave = 0.0
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cor = QColor(tema.atual.destaque)
        passo = self.LARGURA_BARRA + self.ESPACO
        n = max(1, min(len(self.valores), int(self.width() / passo)))
        visiveis = list(self.valores)[-n:]
        larg = self.LARGURA_BARRA
        meio = self.height() / 2
        x0 = self.width() - n * passo + self.ESPACO / 2          # a voz mais nova fica na direita
        for i, v in enumerate(visiveis):
            altura = max(3.0, v * (self.height() - 6))
            c = QColor(cor)
            c.setAlphaF(0.30 + 0.70 * (i + 1) / n)               # as mais antigas ficam mais apagadas
            p.setBrush(c)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x0 + i * passo, meio - altura / 2, larg, altura), larg / 2, larg / 2)
        p.end()


def formatar_tempo(segundos: float) -> str:
    s = int(segundos)
    return f"{s // 60}:{s % 60:02d}"


class BarraGravacao(QFrame):
    """Aparece no lugar da caixa de texto enquanto a pessoa grava: cancelar, onda, tempo e confirmar."""
    confirmar = Signal()
    cancelar = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("barraGravacao")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        self.btn_cancelar = QPushButton("Cancelar")
        self.onda = OndaVoz()
        self.rotulo = QLabel("0:00")
        self.rotulo.setMinimumWidth(40)
        self.btn_ok = QPushButton("Transcrever")
        self.btn_ok.setObjectName("primario")
        self.onda.setMaximumWidth(460)
        lay.addWidget(self.btn_cancelar)
        lay.addStretch(1)
        lay.addWidget(self.onda, 4)
        lay.addWidget(self.rotulo)
        lay.addStretch(1)
        lay.addWidget(self.btn_ok)
        self.btn_cancelar.clicked.connect(self.cancelar)
        self.btn_ok.clicked.connect(self.confirmar)
        self.setStyleSheet(f"#barraGravacao {{ border: 1px solid {tema.atual.destaque}; border-radius: 10px; }}")

    def comecar(self) -> None:
        self.rotulo.setText("0:00")
        self.onda.iniciar()
        self.show()

    def encerrar(self) -> None:
        self.onda.parar()
        self.hide()

    def definir_tempo(self, segundos: float) -> None:
        self.rotulo.setText(formatar_tempo(segundos))
