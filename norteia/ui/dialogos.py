"""Janelinhas de diálogo: filtro salvo e configuração da sincronização."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QObject, QRunnable, QThreadPool, QTime, Qt, Signal
from PySide6.QtGui import QColor, QPixmap, QIcon
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QRadioButton, QSpinBox, QTimeEdit, QVBoxLayout, QWidget)

from .. import autostart
from ..core import Filtro, filtros, recorrencia
from ..core import exportacao
from ..core.assinaturas import CORES as CORES_ASSINATURA
from ..core.assinaturas import ErroAssinatura, baixar, normalizar_url

PALETA = ["#f0524a", "#f5a623", "#4dd0b1", "#4772fa", "#b57edc", "#e8e8e8", "#e86fa9", "#7bc86c"]


def _botoes_ok(dialogo, rotulo_ok="Salvar"):
    caixa = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    caixa.button(QDialogButtonBox.Ok).setText(rotulo_ok)
    caixa.button(QDialogButtonBox.Cancel).setText("Cancelar")
    caixa.accepted.connect(dialogo.accept)
    caixa.rejected.connect(dialogo.reject)
    return caixa


class SeletorCor(QWidget):
    """Fileira de bolinhas coloridas; uma fica marcada."""

    def __init__(self, cor: str = PALETA[2], cores: list[str] | None = None):
        super().__init__()
        self._cores = list(cores or PALETA)
        if cor not in self._cores:
            self._cores.append(cor)
        self._cor = cor
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.botoes: dict[str, QPushButton] = {}
        for c in self._cores:
            b = QPushButton()
            b.setFixedSize(24, 24)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, x=c: self.definir(x))
            lay.addWidget(b)
            self.botoes[c] = b
        lay.addStretch(1)
        self.definir(cor)

    def definir(self, cor: str):
        self._cor = cor
        for c, b in self.botoes.items():
            b.setChecked(c == cor)
            borda = "#ffffff" if c == cor else "transparent"
            b.setStyleSheet(f"QPushButton {{ background: {c}; border: 2px solid {borda}; border-radius: 12px; "
                            f"padding: 0; }} QPushButton:hover {{ border: 2px solid #ffffff; }}")

    def cor(self) -> str:
        return self._cor


class DialogoRepeticao(QDialog):
    """Repetição personalizada: a cada N dias/semanas/meses/anos, em certos dias da semana, com ou sem fim."""

    def __init__(self, parent, regra: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Repetição personalizada")
        self.setMinimumWidth(420)
        base = recorrencia.analisar(regra) or {"freq": "WEEKLY", "intervalo": 1, "dias": [], "ate": None,
                                                "vezes": None}
        lay = QVBoxLayout(self)
        linha = QHBoxLayout()
        linha.addWidget(QLabel("Repetir a cada"))
        self.intervalo = QSpinBox()
        self.intervalo.setRange(1, 99)
        self.intervalo.setValue(base["intervalo"])
        linha.addWidget(self.intervalo)
        self.freq = QComboBox()
        for chave, nome in recorrencia.FREQUENCIAS.items():
            self.freq.addItem(nome, chave)
        self.freq.setCurrentIndex(max(self.freq.findData(base["freq"]), 0))
        linha.addWidget(self.freq, 1)
        lay.addLayout(linha)
        self.rotulo_dias = QLabel("Nos dias")
        lay.addWidget(self.rotulo_dias)
        self.dias_w = QWidget()
        h = QHBoxLayout(self.dias_w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        self.dias: list[QPushButton] = []
        for i, nome in enumerate(["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]):
            b = QPushButton(nome)
            b.setCheckable(True)
            b.setChecked(i in base["dias"])
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("QPushButton { padding: 6px 4px; } QPushButton:checked { background: #4772fa; "
                            "border: 1px solid #4772fa; color: white; }")
            self.dias.append(b)
            h.addWidget(b)
        lay.addWidget(self.dias_w)
        lay.addWidget(QLabel("Termina"))
        self.nunca = QRadioButton("Nunca")
        self.em_data = QRadioButton("Em")
        self.apos = QRadioButton("Depois de")
        self.data_fim = QDateEdit()
        self.data_fim.setCalendarPopup(True)
        self.data_fim.setDisplayFormat("dd/MM/yyyy")
        fim = base["ate"] or date.today()
        self.data_fim.setDate(QDate(fim.year, fim.month, fim.day))
        self.vezes = QSpinBox()
        self.vezes.setRange(1, 999)
        self.vezes.setValue(base["vezes"] or 10)
        l1, l2 = QHBoxLayout(), QHBoxLayout()
        l1.addWidget(self.em_data)
        l1.addWidget(self.data_fim, 1)
        l2.addWidget(self.apos)
        l2.addWidget(self.vezes)
        l2.addWidget(QLabel("vezes"))
        l2.addStretch(1)
        lay.addWidget(self.nunca)
        lay.addLayout(l1)
        lay.addLayout(l2)
        (self.em_data if base["ate"] else self.apos if base["vezes"] else self.nunca).setChecked(True)
        self.resumo = QLabel("")
        self.resumo.setObjectName("mensagemVazia")
        lay.addWidget(self.resumo)
        lay.addWidget(_botoes_ok(self, "Aplicar"))
        self.freq.currentIndexChanged.connect(self._atualizar)
        self.intervalo.valueChanged.connect(self._atualizar)
        for b in self.dias + [self.nunca, self.em_data, self.apos]:
            b.toggled.connect(self._atualizar)
        self.data_fim.dateChanged.connect(self._atualizar)
        self.vezes.valueChanged.connect(self._atualizar)
        self._atualizar()

    def resultado(self) -> str:
        ate = self.data_fim.date()
        return recorrencia.construir(
            self.freq.currentData(), self.intervalo.value(),
            [i for i, b in enumerate(self.dias) if b.isChecked()],
            ate=date(ate.year(), ate.month(), ate.day()) if self.em_data.isChecked() else None,
            vezes=self.vezes.value() if self.apos.isChecked() else None)

    def _atualizar(self, *_):
        semanal = self.freq.currentData() == "WEEKLY"
        self.rotulo_dias.setVisible(semanal)
        self.dias_w.setVisible(semanal)
        self.data_fim.setEnabled(self.em_data.isChecked())
        self.vezes.setEnabled(self.apos.isChecked())
        self.resumo.setText(recorrencia.descrever(self.resultado()))


class _Bolinha(QLabel):
    """Círculo colorido com a inicial do hábito (o 'ícone' do hábito)."""

    def __init__(self, cor: str):
        super().__init__("?")
        self.setFixedSize(44, 44)
        self.setAlignment(Qt.AlignCenter)
        self.cor = cor
        self.definir(cor, "")

    def definir(self, cor: str, nome: str):
        self.cor = cor
        self.setText((nome.strip()[:1] or "?").upper())
        self.setStyleSheet(f"background: {cor}; color: #1c1c1c; border-radius: 22px; font-size: 18px; "
                           f"font-weight: 700;")


class DialogoHabito(QDialog):
    PRESETS = {"Todos os dias": [0, 1, 2, 3, 4, 5, 6], "Dias úteis": [0, 1, 2, 3, 4], "Fim de semana": [5, 6]}
    LETRAS = ["S", "T", "Q", "Q", "S", "S", "D"]
    NOMES = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

    def __init__(self, parent, habito=None):
        super().__init__(parent)
        from ..core.habitos import SECOES
        self.setWindowTitle("Criar Hábito" if habito is None else "Editar Hábito")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(12)
        titulo = QLabel("Criar Hábito" if habito is None else "Editar Hábito")
        titulo.setStyleSheet("font-size: 16px; font-weight: 700;")
        lay.addWidget(titulo)

        topo = QHBoxLayout()
        topo.setSpacing(12)
        cor0 = habito.cor if habito else PALETA[2]
        self.bolinha = _Bolinha(cor0)
        topo.addWidget(self.bolinha)
        self.nome = QLineEdit(habito.nome if habito else "")
        self.nome.setPlaceholderText("Nome do hábito, ex.: Beber água")
        topo.addWidget(self.nome, 1)
        lay.addLayout(topo)
        self.cor = SeletorCor(cor0)
        lay.addWidget(self.cor)
        self.nome.textChanged.connect(lambda t: self.bolinha.definir(self.cor.cor(), t))

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft)

        # Frequência
        marcados = habito.dias if habito else list(range(7))
        self.frequencia = QComboBox()
        self.frequencia.addItems(list(self.PRESETS) + ["Personalizado"])
        self.dias: list[QPushButton] = []
        caixa = QHBoxLayout()
        caixa.setSpacing(6)
        for i, letra in enumerate(self.LETRAS):
            b = QPushButton(letra)
            b.setCheckable(True)
            b.setChecked(i in marcados)
            b.setFixedSize(32, 32)
            b.setToolTip(self.NOMES[i])
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("QPushButton { padding: 0; border-radius: 16px; } "
                            "QPushButton:checked { background: #4772fa; border: 1px solid #4772fa; color: white; }")
            b.toggled.connect(self._dias_mudaram)
            self.dias.append(b)
            caixa.addWidget(b)
        caixa.addStretch(1)
        coluna_freq = QVBoxLayout()
        coluna_freq.setSpacing(8)
        coluna_freq.addWidget(self.frequencia)
        coluna_freq.addLayout(caixa)
        form.addRow("Frequência", coluna_freq)
        self.frequencia.currentTextChanged.connect(self._preset)
        self._dias_mudaram()

        # Objetivo
        self.objetivo = QComboBox()
        self.objetivo.addItems(["Conquiste tudo", "Alcance uma quantidade"])
        self.meta = QSpinBox()
        self.meta.setRange(1, 99)
        self.meta.setValue(habito.meta if habito else 1)
        self.unidade = QLineEdit(habito.unidade if habito else "vez")
        self.unidade.setMaximumWidth(120)
        linha_obj = QHBoxLayout()
        linha_obj.addWidget(self.meta)
        linha_obj.addWidget(self.unidade)
        linha_obj.addWidget(QLabel("por dia"))
        linha_obj.addStretch(1)
        self.quadro_meta = QWidget()
        self.quadro_meta.setLayout(linha_obj)
        linha_obj.setContentsMargins(0, 0, 0, 0)
        coluna_obj = QVBoxLayout()
        coluna_obj.setSpacing(8)
        coluna_obj.addWidget(self.objetivo)
        coluna_obj.addWidget(self.quadro_meta)
        form.addRow("Objetivo", coluna_obj)
        self.objetivo.setCurrentIndex(1 if habito and habito.meta > 1 else 0)
        self.objetivo.currentIndexChanged.connect(self._objetivo_mudou)
        self.meta.valueChanged.connect(lambda v: self.objetivo.setCurrentIndex(1) if v > 1 else None)
        self._objetivo_mudou()

        # Data de início e dias de meta
        self.inicio = QDateEdit()
        self.inicio.setCalendarPopup(True)
        self.inicio.setDisplayFormat("dd/MM/yyyy")
        d0 = habito.inicio if habito else date.today()
        self.inicio.setDate(QDate(d0.year, d0.month, d0.day))
        form.addRow("Data de início", self.inicio)
        self.meta_dias = QComboBox()
        self.meta_dias.addItems(["Para sempre", "Personalizado"])
        self.qtd_dias = QSpinBox()
        self.qtd_dias.setRange(1, 3650)
        self.qtd_dias.setSuffix(" dias")
        self.qtd_dias.setValue(habito.dias_meta if habito and habito.dias_meta else 21)
        linha_md = QHBoxLayout()
        linha_md.addWidget(self.meta_dias, 1)
        linha_md.addWidget(self.qtd_dias)
        self.meta_dias.setCurrentIndex(1 if habito and habito.dias_meta else 0)
        self.qtd_dias.setVisible(self.meta_dias.currentIndex() == 1)
        self.meta_dias.currentIndexChanged.connect(lambda i: self.qtd_dias.setVisible(i == 1))
        form.addRow("Dias de meta", linha_md)

        # Seção
        self.secao = QComboBox()
        self.secao.addItems(SECOES)
        self.secao.setCurrentText(habito.secao if habito else "Outros")
        form.addRow("Seção", self.secao)

        # Lembrete
        self.com_lembrete = QCheckBox("Lembrar às")
        self.hora = QTimeEdit()
        self.hora.setDisplayFormat("HH:mm")
        h, m = (int(x) for x in (habito.lembrete if habito and habito.lembrete else "20:00").split(":"))
        self.hora.setTime(QTime(h, m))
        self.com_lembrete.setChecked(bool(habito and habito.lembrete))
        self.hora.setEnabled(self.com_lembrete.isChecked())
        self.com_lembrete.toggled.connect(self.hora.setEnabled)
        linha2 = QHBoxLayout()
        linha2.addWidget(self.com_lembrete)
        linha2.addWidget(self.hora)
        linha2.addStretch(1)
        form.addRow("Lembrete", linha2)
        lay.addLayout(form)

        self.aviso = QLabel("")
        self.aviso.setObjectName("mensagemVazia")
        lay.addWidget(self.aviso)
        caixa_ok = _botoes_ok(self)
        caixa_ok.accepted.disconnect()
        caixa_ok.accepted.connect(self._confirmar)
        lay.addWidget(caixa_ok)
        self._ligar_cor()

    def _ligar_cor(self):
        """A bolinha acompanha a cor escolhida (SeletorCor não tem sinal; ligamos nos botões)."""
        for c, b in self.cor.botoes.items():
            b.clicked.connect(lambda _=False, x=c: self.bolinha.definir(x, self.nome.text()))
        self.bolinha.definir(self.cor.cor(), self.nome.text())

    def _preset(self, texto: str):
        dias = self.PRESETS.get(texto)
        if dias is None:
            return
        for i, b in enumerate(self.dias):
            b.blockSignals(True)
            b.setChecked(i in dias)
            b.blockSignals(False)

    def _dias_mudaram(self, *_):
        atuais = [i for i, b in enumerate(self.dias) if b.isChecked()]
        nome = next((n for n, d in self.PRESETS.items() if d == atuais), "Personalizado")
        self.frequencia.blockSignals(True)
        self.frequencia.setCurrentText(nome)
        self.frequencia.blockSignals(False)

    def _objetivo_mudou(self, *_):
        self.quadro_meta.setVisible(self.objetivo.currentIndex() == 1)

    def _confirmar(self):
        if not self.nome.text().strip():
            self.aviso.setText("Dê um nome ao hábito.")
        elif not any(b.isChecked() for b in self.dias):
            self.aviso.setText("Marque pelo menos um dia da semana.")
        else:
            self.accept()

    def resultado(self) -> dict:
        d = self.inicio.date()
        quantidade = self.objetivo.currentIndex() == 1
        return {"nome": self.nome.text().strip(), "cor": self.cor.cor(),
                "meta": self.meta.value() if quantidade else 1,
                "unidade": (self.unidade.text().strip() or "vez") if quantidade else "vez",
                "dias": [i for i, b in enumerate(self.dias) if b.isChecked()],
                "lembrete": self.hora.time().toString("HH:mm") if self.com_lembrete.isChecked() else None,
                "inicio": date(d.year(), d.month(), d.day()), "secao": self.secao.currentText(),
                "dias_meta": self.qtd_dias.value() if self.meta_dias.currentIndex() == 1 else 0}


class DialogoContagem(QDialog):
    def __init__(self, parent, contagem=None):
        super().__init__(parent)
        self.setWindowTitle("Nova contagem regressiva" if contagem is None else "Editar contagem")
        self.setMinimumWidth(400)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)
        self.nome = QLineEdit(contagem.nome if contagem else "")
        self.nome.setPlaceholderText("ex.: Prova de SAD")
        form.addRow("Nome", self.nome)
        self.data = QDateEdit()
        self.data.setCalendarPopup(True)
        self.data.setDisplayFormat("dd/MM/yyyy")
        d = contagem.data if contagem else date.today()
        self.data.setDate(QDate(d.year, d.month, d.day))
        form.addRow("Data", self.data)
        self.cor = SeletorCor(contagem.cor if contagem else PALETA[1])
        form.addRow("Cor", self.cor)
        self.anual = QCheckBox("Repete todo ano (aniversário)")
        self.anual.setChecked(bool(contagem and contagem.anual))
        form.addRow(self.anual)
        lay.addLayout(form)
        self.aviso = QLabel("")
        self.aviso.setObjectName("mensagemVazia")
        lay.addWidget(self.aviso)
        caixa = _botoes_ok(self)
        caixa.accepted.disconnect()
        caixa.accepted.connect(self._confirmar)
        lay.addWidget(caixa)

    def _confirmar(self):
        if not self.nome.text().strip():
            self.aviso.setText("Dê um nome à contagem.")
        else:
            self.accept()

    def resultado(self) -> dict:
        q = self.data.date()
        return {"nome": self.nome.text().strip(), "data": date(q.year(), q.month(), q.day()),
                "cor": self.cor.cor(), "anual": self.anual.isChecked()}


class _SinaisBaixa(QObject):
    pronto = Signal(int, object, object)        # assinatura, texto, erro


class _Baixa(QRunnable):
    def __init__(self, assinatura_id, url, baixar_fn, sinais):
        super().__init__()
        self.args = (assinatura_id, url, baixar_fn, sinais)

    def run(self):
        assinatura_id, url, baixar_fn, sinais = self.args
        try:
            sinais.pronto.emit(assinatura_id, baixar_fn(url), None)
        except Exception as e:  # noqa: BLE001 - qualquer falha vira mensagem na tela
            sinais.pronto.emit(assinatura_id, None, e)


class DialogoNovaAssinatura(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Adicionar calendário")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Cole o endereço .ics do calendário. No Google Agenda: Configurações do calendário > "
                             "\"Endereço secreto no formato iCal\". Quem tem esse endereço enxerga o calendário, "
                             "então não compartilhe."))
        lay.itemAt(0).widget().setWordWrap(True)
        form = QFormLayout()
        self.nome = QLineEdit()
        self.nome.setPlaceholderText("ex.: Google Agenda, Feriados")
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://calendar.google.com/calendar/ical/.../basic.ics")
        form.addRow("Nome", self.nome)
        form.addRow("Endereço", self.url)
        lay.addLayout(form)
        self.aviso = QLabel("")
        self.aviso.setObjectName("mensagemVazia")
        lay.addWidget(self.aviso)
        caixa = _botoes_ok(self, "Adicionar")
        caixa.accepted.disconnect()
        caixa.accepted.connect(self._confirmar)
        lay.addWidget(caixa)

    def _confirmar(self):
        try:
            normalizar_url(self.url.text())
        except ErroAssinatura as e:
            self.aviso.setText(str(e))
            return
        self.accept()

    def resultado(self) -> tuple[str, str]:
        return self.nome.text().strip(), self.url.text().strip()


class DialogoAssinaturas(QDialog):
    """Calendários externos (somente leitura) que aparecem no calendário."""

    def __init__(self, parent, servico, baixar_fn=baixar, em_thread: bool = True):
        super().__init__(parent)
        self.servico, self._baixar, self._em_thread = servico, baixar_fn, em_thread
        self.setWindowTitle("Calendários externos")
        self.setMinimumSize(520, 360)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Eventos do Google Agenda, Outlook ou feriados, só para ver (não dá para editar aqui)."))
        self.lista = QListWidget()
        lay.addWidget(self.lista, 1)
        linha = QHBoxLayout()
        self.btn_add = QPushButton("Adicionar...")
        self.btn_atualizar = QPushButton("Atualizar agora")
        self.btn_remover = QPushButton("Remover")
        for b in (self.btn_add, self.btn_atualizar, self.btn_remover):
            linha.addWidget(b)
        linha.addStretch(1)
        lay.addLayout(linha)
        self.status = QLabel("")
        self.status.setObjectName("mensagemVazia")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        fechar = QDialogButtonBox(QDialogButtonBox.Close)
        fechar.button(QDialogButtonBox.Close).setText("Fechar")
        fechar.rejected.connect(self.accept)
        fechar.accepted.connect(self.accept)
        lay.addWidget(fechar)
        self._sinais = _SinaisBaixa()
        self._sinais.pronto.connect(self._baixou)
        self.btn_add.clicked.connect(self.adicionar)
        self.btn_remover.clicked.connect(self.remover)
        self.btn_atualizar.clicked.connect(self.atualizar_todos)
        self.mudou = False
        self._recarregar()

    def _recarregar(self):
        self.lista.clear()
        for a in self.servico.assinaturas("ics"):
            quando = a["ultima_sync"][:16].replace("T", " ") if a["ultima_sync"] else "nunca atualizado"
            it = QListWidgetItem(f"{a['nome']}   ·   {quando}" + (f"   ·   erro: {a['erro']}" if a["erro"] else ""))
            it.setData(Qt.UserRole, a["id"])
            pm = QPixmap(14, 14)
            pm.fill(QColor(a["cor"]))
            it.setIcon(QIcon(pm))
            self.lista.addItem(it)

    def adicionar(self, nome: str | None = None, url: str | None = None):
        if nome is None:
            dlg = DialogoNovaAssinatura(self)
            if dlg.exec() != QDialog.Accepted:
                return
            nome, url = dlg.resultado()
        ass_id = self.servico.assin.adicionar(nome, url)
        self.mudou = True
        self._recarregar()
        self._buscar(ass_id)

    def remover(self):
        item = self.lista.currentItem()
        if item is not None:
            self.servico.assin.remover(item.data(Qt.UserRole))
            self.mudou = True
            self._recarregar()

    def atualizar_todos(self):
        for a in self.servico.assinaturas("ics"):
            self._buscar(a["id"])

    def _buscar(self, ass_id: int):
        ass = next(a for a in self.servico.assinaturas() if a["id"] == ass_id)
        self.status.setText(f"Baixando “{ass['nome']}”...")
        if self._em_thread:
            QThreadPool.globalInstance().start(_Baixa(ass_id, ass["url"], self._baixar, self._sinais))
        else:
            try:
                self._baixou(ass_id, self._baixar(ass["url"]), None)
            except Exception as e:  # noqa: BLE001
                self._baixou(ass_id, None, e)

    def _baixou(self, ass_id: int, texto, erro):
        if erro is not None:
            self.servico.assin.registrar_erro(ass_id, str(erro))
            self.status.setText(f"Não consegui atualizar: {erro}")
        else:
            n = self.servico.assin.aplicar_texto(ass_id, texto)
            self.status.setText(f"Pronto: {n} evento(s) carregado(s).")
            self.mudou = True
        self._recarregar()


class DialogoDados(QDialog):
    """Backup, importação e exportação."""

    def __init__(self, parent, servico, ao_mudar=None):
        super().__init__(parent)
        self.servico, self._ao_mudar = servico, ao_mudar
        self.setWindowTitle("Importar e exportar")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Exportar"))
        for texto, funcao in (("Backup completo (.json)", self.exportar_backup),
                              ("Planilha de tarefas (.csv, abre no Excel)", self.exportar_csv),
                              ("Calendário (.ics, para Google Agenda e Outlook)", self.exportar_ics)):
            b = QPushButton(texto)
            b.clicked.connect(lambda _=False, f=funcao: f())
            lay.addWidget(b)
        lay.addSpacing(8)
        lay.addWidget(QLabel("Importar"))
        for texto, funcao in (("Backup (.json)", self.importar_backup),
                              ("Tarefas (.csv deste app ou de outros apps de tarefas)", self.importar_csv),
                              ("Calendário (.ics)", self.importar_ics)):
            b = QPushButton(texto)
            b.clicked.connect(lambda _=False, f=funcao: f())
            lay.addWidget(b)
        self.status = QLabel("")
        self.status.setObjectName("mensagemVazia")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        fechar = QDialogButtonBox(QDialogButtonBox.Close)
        fechar.button(QDialogButtonBox.Close).setText("Fechar")
        fechar.rejected.connect(self.accept)
        lay.addWidget(fechar)

    # ---- exportar ----
    def _salvar(self, titulo: str, nome: str, filtro: str, conteudo: str, codificacao="utf-8", caminho=None):
        if caminho is None:
            caminho, _ = QFileDialog.getSaveFileName(self, titulo, nome, filtro)
        if not caminho:
            return None
        with open(caminho, "w", encoding=codificacao, newline="") as f:
            f.write(conteudo)
        self.status.setText(f"Salvo em {caminho}")
        return caminho

    def exportar_backup(self, caminho=None):
        return self._salvar("Salvar backup", f"tarefas-backup-{date.today():%Y-%m-%d}.json", "Backup (*.json)",
                            exportacao.exportar_json(self.servico), caminho=caminho)

    def exportar_csv(self, caminho=None):
        return self._salvar("Salvar planilha", "tarefas.csv", "Planilha (*.csv)",
                            exportacao.exportar_csv(self.servico), caminho=caminho)

    def exportar_ics(self, caminho=None):
        return self._salvar("Salvar calendário", "tarefas.ics", "Calendário (*.ics)",
                            exportacao.exportar_ics(self.servico), caminho=caminho)

    # ---- importar ----
    def _ler(self, titulo: str, filtro: str, caminho=None) -> str | None:
        if caminho is None:
            caminho, _ = QFileDialog.getOpenFileName(self, titulo, "", filtro)
        if not caminho:
            return None
        with open(caminho, "rb") as f:
            bruto = f.read()
        try:
            return bruto.decode("utf-8-sig")
        except UnicodeDecodeError:
            return bruto.decode("latin-1")

    def _concluir(self, resultado) -> None:
        texto = str(resultado) + ("  " + " ".join(resultado.avisos) if resultado.avisos else "")
        self.status.setText(texto)
        if self._ao_mudar:
            self._ao_mudar()

    def _tentar(self, funcao, texto):
        try:
            self._concluir(funcao(self.servico, texto))
        except ValueError as e:
            self.status.setText(f"Não deu certo: {e}")
            QMessageBox.warning(self, "Importar", str(e))

    def importar_backup(self, caminho=None):
        texto = self._ler("Abrir backup", "Backup (*.json)", caminho)
        if texto is not None:
            self._tentar(exportacao.importar_json, texto)

    def importar_csv(self, caminho=None):
        texto = self._ler("Abrir planilha", "Planilha (*.csv)", caminho)
        if texto is not None:
            self._tentar(exportacao.importar_csv, texto)

    def importar_ics(self, caminho=None):
        texto = self._ler("Abrir calendário", "Calendário (*.ics)", caminho)
        if texto is not None:
            self._tentar(exportacao.importar_ics, texto)


class DialogoFiltro(QDialog):
    PRIORIDADES = [("Qualquer prioridade", 0), ("Baixa ou maior", 1), ("Média ou maior", 2), ("Só alta", 3)]

    def __init__(self, parent, projetos, etiquetas, filtro: Filtro | None = None):
        super().__init__(parent)
        self.setWindowTitle("Novo filtro" if filtro is None else "Editar filtro")
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Mostre só as tarefas que combinam com tudo o que você marcar."))
        form = QFormLayout()
        form.setSpacing(10)
        self.nome = QLineEdit()
        self.nome.setPlaceholderText("ex.: Urgentes da semana")
        form.addRow("Nome", self.nome)
        self.lista = QComboBox()
        self.lista.addItem("Qualquer lista", None)
        for p in projetos:
            self.lista.addItem(p.nome, p.id)
        form.addRow("Lista", self.lista)
        self.etiqueta = QComboBox()
        self.etiqueta.addItem("Qualquer etiqueta", None)
        for g in etiquetas:
            self.etiqueta.addItem("#" + g.nome, g.nome)
        form.addRow("Etiqueta", self.etiqueta)
        self.prioridade = QComboBox()
        for nome, valor in self.PRIORIDADES:
            self.prioridade.addItem(nome, valor)
        form.addRow("Prioridade", self.prioridade)
        self.prazo = QComboBox()
        for nome, valor in filtros.PRAZOS:
            self.prazo.addItem(nome, valor)
        form.addRow("Data", self.prazo)
        self.texto = QLineEdit()
        self.texto.setPlaceholderText("palavra no título ou nas notas (opcional)")
        form.addRow("Contém", self.texto)
        lay.addLayout(form)
        self.aviso = QLabel("")
        self.aviso.setObjectName("mensagemVazia")
        lay.addWidget(self.aviso)
        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.button(QDialogButtonBox.Ok).setText("Salvar")
        botoes.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botoes.accepted.connect(self._confirmar)
        botoes.rejected.connect(self.reject)
        lay.addWidget(botoes)
        if filtro is not None:
            self._preencher(filtro)

    def _preencher(self, f: Filtro):
        c = f.criterios
        self.nome.setText(f.nome)
        self.lista.setCurrentIndex(max(self.lista.findData(c.get("projeto_id")), 0))
        self.etiqueta.setCurrentIndex(max(self.etiqueta.findData(c.get("tag")), 0))
        self.prioridade.setCurrentIndex(max(self.prioridade.findData(int(c.get("prioridade_min", 0) or 0)), 0))
        self.prazo.setCurrentIndex(max(self.prazo.findData(c.get("prazo")), 0))
        self.texto.setText(c.get("texto", ""))

    def _confirmar(self):
        if not self.nome.text().strip():
            self.aviso.setText("Dê um nome ao filtro.")
            return
        self.accept()

    def resultado(self) -> tuple[str, dict]:
        criterios = {}
        if self.lista.currentData() is not None:
            criterios["projeto_id"] = self.lista.currentData()
        if self.etiqueta.currentData():
            criterios["tag"] = self.etiqueta.currentData()
        if self.prioridade.currentData():
            criterios["prioridade_min"] = self.prioridade.currentData()
        if self.prazo.currentData():
            criterios["prazo"] = self.prazo.currentData()
        if self.texto.text().strip():
            criterios["texto"] = self.texto.text().strip()
        return self.nome.text().strip(), criterios


class DialogoSincronizacao(QDialog):
    def __init__(self, parent, url: str = "", token: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Sincronização")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Endereço e senha do seu servidor de sincronização.\n"
                             "Deixe em branco para usar só neste computador."))
        form = QFormLayout()
        form.setSpacing(10)
        self.url = QLineEdit(url)
        self.url.setPlaceholderText("http://100.x.y.z:8765")
        form.addRow("Servidor", self.url)
        self.token = QLineEdit(token)
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText("a mesma senha (NORTEIA_TOKEN) do servidor")
        form.addRow("Senha", self.token)
        lay.addLayout(form)
        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.button(QDialogButtonBox.Ok).setText("Salvar")
        botoes.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        lay.addWidget(botoes)

    def resultado(self) -> tuple[str, str]:
        return self.url.text().strip(), self.token.text().strip()


class DialogoConfiguracoes(QDialog):
    """Preferências de notificação (ficam em ~/.tarefas/config.json)."""

    def __init__(self, parent, prefs: dict):
        super().__init__(parent)
        self.setWindowTitle("Configurações")
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Notificações"))
        form = QFormLayout()
        form.setSpacing(10)
        self.aviso_na_tela = QCheckBox("Mostrar a janelinha de lembrete (com Adiar e Concluir)")
        self.aviso_na_tela.setChecked(bool(prefs.get("aviso_na_tela", True)))
        form.addRow(self.aviso_na_tela)
        self.bandeja = QCheckBox("Continuar rodando na bandeja ao fechar a janela (recomendado)")
        self.bandeja.setChecked(bool(prefs.get("fechar_para_bandeja", True)))
        form.addRow(self.bandeja)
        self.iniciar = QCheckBox("Abrir junto com o Windows")
        self.iniciar.setChecked(bool(prefs.get("iniciar_com_windows", False)))
        self.iniciar.setVisible(autostart.disponivel())
        form.addRow(self.iniciar)
        self.segunda = QCheckBox("Semana começa na segunda-feira (no calendário)")
        self.segunda.setChecked(bool(prefs.get("semana_comeca_segunda", False)))
        form.addRow(self.segunda)
        self.resumo = QCheckBox("Resumo do dia")
        self.resumo.setChecked(bool(prefs.get("resumo_diario", True)))
        form.addRow(self.resumo)
        self.hora_resumo = QTimeEdit()
        self.hora_resumo.setDisplayFormat("HH:mm")
        h, m = (int(x) for x in str(prefs.get("resumo_hora", "08:00")).split(":"))
        self.hora_resumo.setTime(QTime(h, m))
        form.addRow("Avisar a partir das", self.hora_resumo)
        lay.addLayout(form)
        lay.addWidget(QLabel("Claude (opcional)"))
        form2 = QFormLayout()
        form2.setSpacing(10)
        self.chave_ia = QLineEdit(str(prefs.get("claude_api_key", "")))
        self.chave_ia.setEchoMode(QLineEdit.Password)
        self.chave_ia.setPlaceholderText("sk-ant-... (fica só neste computador)")
        self.modelo_ia = QLineEdit(str(prefs.get("claude_modelo", "")))
        self.modelo_ia.setPlaceholderText("vazio = modelo padrão")
        form2.addRow("Chave da API", self.chave_ia)
        form2.addRow("Modelo", self.modelo_ia)
        lay.addLayout(form2)
        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        lay.addWidget(botoes)

    def resultado(self) -> dict:
        return {
            "aviso_na_tela": self.aviso_na_tela.isChecked(),
            "fechar_para_bandeja": self.bandeja.isChecked(),
            "iniciar_com_windows": self.iniciar.isChecked(),
            "resumo_diario": self.resumo.isChecked(),
            "resumo_hora": self.hora_resumo.time().toString("HH:mm"),
            "semana_comeca_segunda": self.segunda.isChecked(),
            "claude_api_key": self.chave_ia.text().strip(),
            "claude_modelo": self.modelo_ia.text().strip(),
        }
