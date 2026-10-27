"""Diálogo "Adicionar lista" (e "Editar lista"): nome com emoji, cor, visualização, pasta, tipo e lista inteligente.

O seletor de emoji é uma janelinha com busca e categorias. Os emojis vêm de uma tabela própria (sem depender de
bibliotecas externas); cada um tem palavras-chave em português para a busca.
"""
from __future__ import annotations

import random

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from . import icones, tema
from .popovers import Flutuante

SEM_COR = "#8a8f98"          # mesma convenção das etiquetas: cinza = sem cor

# categoria -> [(emoji, "palavras de busca")]
EMOJIS: dict[str, list[tuple[str, str]]] = {
    "Pessoas": [
        ("😀", "sorriso feliz alegre"), ("😃", "sorriso feliz"), ("😄", "sorriso rir"), ("😁", "sorriso dentes"),
        ("😆", "rir gargalhada"), ("😅", "suor alivio"), ("🤣", "rir chorando"), ("😂", "rir lagrimas"),
        ("🙂", "sorriso leve"), ("😉", "piscada"), ("😊", "feliz corar"), ("😇", "anjo santo"),
        ("🥰", "amor apaixonado"), ("😍", "amor olhos coracao"), ("🤩", "estrela deslumbrado"),
        ("😘", "beijo"), ("😋", "gostoso saboroso"), ("😛", "lingua"), ("🤔", "pensar duvida"),
        ("🤨", "desconfiado"), ("😐", "neutro"), ("😴", "sono dormir"), ("😎", "oculos legal"),
        ("🤓", "nerd estudo"), ("🧐", "monoculo investigar"), ("😭", "chorar"), ("😤", "irritado"),
        ("😡", "raiva bravo"), ("🥳", "festa aniversario"), ("🤯", "cabeca explodindo"), ("😱", "susto medo"),
        ("🤗", "abraco"), ("🙌", "maos celebrar"), ("👍", "joinha ok bom"), ("👎", "ruim nao"),
        ("👏", "palmas aplauso"), ("🙏", "obrigado rezar por favor"), ("💪", "forca musculo treino"),
        ("🧠", "cerebro mente estudo"), ("👀", "olhos ver"), ("👨‍💻", "programador computador trabalho"),
        ("👩‍⚖️", "advogada juiza lei"), ("👨‍⚕️", "medico saude"), ("🧑‍🎓", "estudante formatura"),
        ("🧑‍🍳", "cozinheiro"), ("🏃", "correr corrida"), ("🧘", "yoga meditacao"), ("🚶", "caminhar"),
    ],
    "Animais": [
        ("🐶", "cachorro cao pet"), ("🐱", "gato pet"), ("🐭", "rato"), ("🐹", "hamster"), ("🐰", "coelho"),
        ("🦊", "raposa"), ("🐻", "urso"), ("🐼", "panda"), ("🐨", "coala"), ("🐯", "tigre"), ("🦁", "leao"),
        ("🐮", "vaca"), ("🐷", "porco"), ("🐸", "sapo"), ("🐵", "macaco"), ("🐔", "galinha"), ("🐧", "pinguim"),
        ("🐦", "passaro"), ("🦉", "coruja sabedoria"), ("🦋", "borboleta"), ("🐝", "abelha"), ("🐞", "joaninha"),
        ("🐢", "tartaruga"), ("🐍", "cobra python"), ("🐙", "polvo"), ("🐬", "golfinho"), ("🐳", "baleia"),
        ("🌳", "arvore natureza"), ("🌵", "cacto"), ("🌻", "girassol flor"), ("🌹", "rosa flor"),
        ("🍀", "trevo sorte"), ("🌱", "planta broto crescer"), ("🌍", "terra mundo"), ("🌙", "lua noite"),
        ("⭐", "estrela"), ("🔥", "fogo"), ("🌈", "arco iris"), ("☀️", "sol"), ("⛈️", "tempestade chuva"),
    ],
    "Comida": [
        ("🍎", "maca fruta"), ("🍌", "banana fruta"), ("🍇", "uva fruta"), ("🍓", "morango fruta"),
        ("🍉", "melancia fruta"), ("🍊", "laranja fruta"), ("🍋", "limao"), ("🍍", "abacaxi"), ("🥑", "abacate"),
        ("🥦", "brocolis legumes"), ("🥕", "cenoura"), ("🌽", "milho"), ("🍞", "pao"), ("🧀", "queijo"),
        ("🥚", "ovo"), ("🍳", "frigideira cozinhar ovo"), ("🥓", "bacon"), ("🍔", "hamburguer lanche"),
        ("🍟", "batata frita"), ("🍕", "pizza"), ("🌭", "cachorro quente"), ("🌮", "taco"), ("🍝", "macarrao"),
        ("🍣", "sushi"), ("🍚", "arroz"), ("🍜", "lamen sopa"), ("🍰", "bolo sobremesa"), ("🍫", "chocolate"),
        ("🍩", "rosquinha"), ("🍪", "biscoito"), ("☕", "cafe"), ("🍵", "cha"), ("🥤", "refrigerante copo"),
        ("🍺", "cerveja"), ("🍷", "vinho"), ("🥗", "salada saudavel"), ("🥩", "carne churrasco"),
    ],
    "Atividades": [
        ("⚽", "futebol bola"), ("🏀", "basquete"), ("🏈", "futebol americano"), ("🎾", "tenis"),
        ("🏐", "volei"), ("🏓", "ping pong"), ("🥊", "boxe luta"), ("🏋️", "academia musculacao treino peso"),
        ("🚴", "bicicleta ciclismo"), ("🏊", "natacao"), ("🏆", "trofeu campeao"), ("🥇", "medalha ouro"),
        ("🎯", "alvo meta foco"), ("🎮", "videogame jogo"), ("🎲", "dado jogo"), ("♟️", "xadrez"),
        ("🎸", "guitarra musica"), ("🎹", "piano teclado"), ("🎧", "fone musica"), ("🎤", "microfone cantar"),
        ("🎬", "cinema filme"), ("🎨", "arte pintura"), ("📸", "foto camera"), ("🎭", "teatro"),
        ("✈️", "aviao viagem"), ("🚗", "carro"), ("🚌", "onibus"), ("🏖️", "praia ferias"),
        ("⛰️", "montanha"), ("🏕️", "acampar"), ("🧳", "mala viagem"), ("🗺️", "mapa"),
    ],
    "Objetos": [
        ("💻", "notebook computador trabalho"), ("🖥️", "computador"), ("⌨️", "teclado"), ("📱", "celular"),
        ("💡", "ideia lampada"), ("🔋", "bateria"), ("📚", "livros estudo faculdade"), ("📖", "livro leitura"),
        ("📝", "anotacao nota escrever"), ("📓", "caderno"), ("✏️", "lapis"), ("📌", "fixar alfinete"),
        ("📎", "clipe anexo"), ("📅", "calendario data"), ("⏰", "despertador alarme"), ("⏳", "ampulheta tempo"),
        ("📧", "email"), ("📞", "telefone ligar"), ("💼", "maleta trabalho"), ("📁", "pasta arquivo"),
        ("🗂️", "organizar fichario"), ("📊", "grafico dados"), ("📈", "crescimento grafico"),
        ("💰", "dinheiro financas"), ("💳", "cartao credito"), ("🧾", "recibo nota fiscal"), ("🏠", "casa"),
        ("🛒", "compras mercado carrinho"), ("🎁", "presente"), ("🔑", "chave"), ("🔒", "cadeado seguranca"),
        ("⚖️", "balanca justica lei advogado"), ("🔧", "ferramenta chave inglesa"), ("🛠️", "ferramentas"),
        ("🧹", "limpeza vassoura"), ("🧺", "roupa lavanderia"), ("💊", "remedio saude"), ("🩺", "saude medico"),
        ("🤖", "robo ia inteligencia artificial"), ("🚀", "foguete lancamento projeto"),
        ("❤️", "coracao amor"), ("✅", "feito concluido check"), ("❗", "importante"), ("🔔", "sino lembrete"),
    ],
}


def todos_os_emojis() -> list[tuple[str, str]]:
    return [par for lista in EMOJIS.values() for par in lista]


class SeletorEmoji(Flutuante):
    """Janelinha com busca, categorias e grade de emojis."""
    escolhido = Signal(str)
    COLUNAS = 9

    def __init__(self, parent=None):
        super().__init__(parent)
        pal = tema.atual
        self.setFixedSize(388, 380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 10)
        lay.setSpacing(8)
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar")
        self.busca.addAction(icones.icone("busca", pal.apagado, 16), QLineEdit.LeadingPosition)
        self.busca.textChanged.connect(self._montar)
        lay.addWidget(self.busca)

        barra = QHBoxLayout()
        barra.setSpacing(2)
        self.cat_btns: dict[str, QPushButton] = {}
        for nome, lista in EMOJIS.items():
            b = QPushButton(lista[0][0])
            b.setObjectName("plano")
            b.setToolTip(nome)
            b.setFixedSize(30, 28)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, n=nome: self._ir_para(n))
            self.cat_btns[nome] = b
            barra.addWidget(b)
        barra.addStretch(1)
        aleatorio = QPushButton("Aleatório")
        aleatorio.setObjectName("plano")
        aleatorio.setCursor(Qt.PointingHandCursor)
        aleatorio.clicked.connect(self._sortear)
        barra.addWidget(aleatorio)
        self.btn_limpar = QPushButton("Reiniciar")
        self.btn_limpar.setObjectName("plano")
        self.btn_limpar.setCursor(Qt.PointingHandCursor)
        self.btn_limpar.setStyleSheet(f"color: {pal.apagado};")
        self.btn_limpar.clicked.connect(lambda: self._escolher(""))
        barra.addWidget(self.btn_limpar)
        lay.addLayout(barra)

        self.rolagem = QScrollArea()
        self.rolagem.setWidgetResizable(True)
        self.rolagem.setFrameShape(QFrame.NoFrame)
        self.rolagem.setStyleSheet("background: transparent;")
        lay.addWidget(self.rolagem, 1)
        self._ancoras: dict[str, int] = {}
        self._montar("")

    def _botao_emoji(self, emoji: str, dica: str) -> QPushButton:
        b = QPushButton(emoji)
        b.setObjectName("plano")
        b.setFixedSize(34, 34)
        b.setToolTip(dica)
        b.setCursor(Qt.PointingHandCursor)
        f = QFont(b.font())
        f.setPixelSize(20)
        b.setFont(f)
        b.clicked.connect(lambda _=False, e=emoji: self._escolher(e))
        return b

    def _montar(self, texto: str):
        texto = texto.strip().lower()
        corpo = QWidget()
        grade = QGridLayout(corpo)
        grade.setContentsMargins(0, 0, 0, 0)
        grade.setSpacing(2)
        self._ancoras = {}
        linha = 0
        pal = tema.atual
        for nome, lista in EMOJIS.items():
            itens = [(e, k) for e, k in lista if not texto or texto in k or texto in nome.lower()]
            if not itens:
                continue
            cab = QLabel(nome)
            cab.setStyleSheet(f"color: {pal.texto}; font-weight: 600; font-size: 13px; padding: 6px 2px 2px 2px;")
            grade.addWidget(cab, linha, 0, 1, self.COLUNAS)
            self._ancoras[nome] = linha
            linha += 1
            for i, (e, k) in enumerate(itens):
                grade.addWidget(self._botao_emoji(e, k.split()[0]), linha + i // self.COLUNAS, i % self.COLUNAS)
            linha += (len(itens) + self.COLUNAS - 1) // self.COLUNAS
        if linha == 0:
            vazio = QLabel("Nenhum emoji encontrado")
            vazio.setAlignment(Qt.AlignCenter)
            vazio.setStyleSheet(f"color: {pal.apagado};")
            grade.addWidget(vazio, 0, 0, 1, self.COLUNAS)
        grade.setRowStretch(linha + 1, 1)
        self.rolagem.setWidget(corpo)
        self._corpo = corpo
        self._grade = grade

    def _ir_para(self, categoria: str):
        if self.busca.text():
            self.busca.clear()
        linha = self._ancoras.get(categoria)
        item = self._grade.itemAtPosition(linha, 0) if linha is not None else None
        if item is not None and item.widget() is not None:
            self.rolagem.verticalScrollBar().setValue(item.widget().y())

    def _sortear(self):
        self._escolher(random.choice(todos_os_emojis())[0])

    def _escolher(self, emoji: str):
        self.escolhido.emit(emoji)
        self.close()


class PreviaVisao(QWidget):
    """Desenho simples de como a lista vai aparecer (lista, quadros ou linha do tempo)."""

    def __init__(self):
        super().__init__()
        self.visao = "lista"
        self.cor = "#4772fa"
        self.setMinimumSize(300, 330)

    def definir(self, visao: str, cor: str):
        self.visao, self.cor = visao, cor
        self.update()

    def paintEvent(self, _):
        pal = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        area = QRectF(24, 40, self.width() - 24, self.height() - 80)
        p.setPen(QPen(QColor(pal.borda), 1))
        p.setBrush(QColor(pal.fundo))
        p.drawRoundedRect(area, 10, 10)
        p.setPen(Qt.NoPen)
        cinza = QColor(pal.borda).lighter(135)
        cor = QColor(self.cor)

        def barra(x, y, w, cheia=False):
            p.setBrush(cor if cheia else cinza)
            p.drawRoundedRect(QRectF(x, y, w, 7), 3, 3)

        def caixinha(x, y):
            p.setPen(QPen(cor, 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(x, y, 9, 9), 2, 2)
            p.setPen(Qt.NoPen)

        x0, y0 = area.left() + 18, area.top() + 20
        if self.visao == "lista":
            barra(x0, y0, 90)
            for i, larg in enumerate((150, 110, 170, 90, 130)):
                caixinha(x0, y0 + 34 + i * 30)
                barra(x0 + 20, y0 + 36 + i * 30, larg, cheia=i == 0)
        elif self.visao == "kanban":
            larg_col = (area.width() - 54) / 2
            for c in range(2):
                x = x0 + c * (larg_col + 12)
                barra(x, y0, 70)
                for i in range(3 - c):
                    p.setBrush(QColor(pal.campo))
                    p.drawRoundedRect(QRectF(x, y0 + 28 + i * 62, larg_col, 50), 6, 6)
                    caixinha(x + 8, y0 + 38 + i * 62)
                    barra(x + 24, y0 + 40 + i * 62, larg_col - 40, cheia=i == 0 and c == 0)
        else:
            for i in range(6):
                barra(x0 + 4, y0 + i * 32, 36)
            for i, (ini, larg) in enumerate(((40, 120), (90, 150), (60, 90), (140, 110), (110, 130), (50, 100))):
                p.setBrush(cor if i % 2 == 0 else cinza)
                p.drawRoundedRect(QRectF(x0 + 52 + ini * 0.6, y0 - 2 + i * 32, larg * 0.7, 14), 5, 5)
        p.end()


class DialogoLista(QDialog):
    """Cria ou edita uma lista."""
    VISOES = [("lista", "lista", "Lista"), ("kanban", "kanban", "Kanban"),
              ("linha_tempo", "linha-tempo", "Linha do tempo")]

    def __init__(self, parent, cores: list[str], pastas: list[str], projeto=None):
        super().__init__(parent)
        pal = tema.atual
        self.setWindowTitle("Editar lista" if projeto is not None else "Adicionar lista")
        self.setModal(True)
        self._cores = list(cores)
        self._cor = (projeto.cor if projeto.cor != SEM_COR else "") if projeto is not None else ""
        self._visao = projeto.visao if projeto is not None else "lista"
        self._emoji = projeto.emoji if projeto is not None else ""
        self._seletor: SeletorEmoji | None = None

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        esq = QWidget()
        esq.setFixedWidth(500)
        lay = QVBoxLayout(esq)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(14)
        titulo = QLabel(self.windowTitle())
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setStyleSheet("font-size: 16px; font-weight: 700;")
        lay.addWidget(titulo)

        linha_nome = QHBoxLayout()
        linha_nome.setSpacing(0)
        self.btn_emoji = QPushButton()
        self.btn_emoji.setObjectName("emojiLista")
        self.btn_emoji.setFixedSize(44, 40)
        self.btn_emoji.setCursor(Qt.PointingHandCursor)
        self.btn_emoji.setToolTip("Escolher um emoji para a lista")
        self.btn_emoji.setStyleSheet(
            f"QPushButton#emojiLista {{ background: {pal.campo}; border: 1px solid {pal.borda}; "
            f"border-right: none; border-top-right-radius: 0; border-bottom-right-radius: 0; font-size: 18px; }}")
        self.btn_emoji.clicked.connect(self._abrir_emojis)
        linha_nome.addWidget(self.btn_emoji)
        self.nome = QLineEdit(projeto.nome if projeto is not None else "")
        self.nome.setPlaceholderText("Nome")
        self.nome.setFixedHeight(40)
        self.nome.setStyleSheet("border-top-left-radius: 0; border-bottom-left-radius: 0; font-size: 15px;")
        self.nome.textChanged.connect(self._validar)
        linha_nome.addWidget(self.nome, 1)
        lay.addLayout(linha_nome)

        grade = QGridLayout()
        grade.setHorizontalSpacing(16)
        grade.setVerticalSpacing(14)
        grade.setColumnMinimumWidth(0, 120)

        def rotulo(texto):
            r = QLabel(texto)
            r.setWordWrap(True)
            return r

        grade.addWidget(rotulo("Cor"), 0, 0)
        cores_box = QHBoxLayout()
        cores_box.setSpacing(8)
        self.bolinhas: list[tuple[str, QPushButton]] = []
        for cor in [""] + self._cores:
            b = QPushButton()
            b.setFixedSize(24, 24)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip("Sem cor" if not cor else cor.upper())
            b.clicked.connect(lambda _=False, c=cor: self._escolher_cor(c))
            cores_box.addWidget(b)
            self.bolinhas.append((cor, b))
        cores_box.addStretch(1)
        grade.addLayout(cores_box, 0, 1)

        grade.addWidget(rotulo("Visualização"), 1, 0)
        vis_box = QHBoxLayout()
        vis_box.setSpacing(10)
        self.btns_visao: dict[str, QPushButton] = {}
        for chave, icone, nome in self.VISOES:
            b = QPushButton()
            b.setCheckable(True)
            b.setFixedSize(62, 44)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(nome)
            b.setIconSize(QSize(24, 24))
            b.clicked.connect(lambda _=False, c=chave: self._escolher_visao(c))
            vis_box.addWidget(b)
            self.btns_visao[chave] = b
        vis_box.addStretch(1)
        grade.addLayout(vis_box, 1, 1)

        grade.addWidget(rotulo("Pasta"), 2, 0)
        self.pasta = QComboBox()
        self.pasta.addItem("Nenhuma", "")
        for nome in pastas:
            self.pasta.addItem(nome, nome)
        self.pasta.addItem("Nova pasta...", "__nova__")
        atual = projeto.pasta if projeto is not None else ""
        if atual and self.pasta.findData(atual) < 0:
            self.pasta.insertItem(self.pasta.count() - 1, atual, atual)
        self.pasta.setCurrentIndex(max(0, self.pasta.findData(atual)))
        self._pasta_anterior = self.pasta.currentIndex()
        self.pasta.activated.connect(self._ao_escolher_pasta)
        grade.addWidget(self.pasta, 2, 1)

        grade.addWidget(rotulo("Tipo"), 3, 0)
        self.tipo = QComboBox()
        self.tipo.addItem("Lista de tarefas", "tarefas")
        self.tipo.addItem("Lista de notas", "notas")
        self.tipo.setCurrentIndex(1 if projeto is not None and projeto.tipo == "notas" else 0)
        grade.addWidget(self.tipo, 3, 1)

        grade.addWidget(rotulo("Mostrar na Lista Inteligente"), 4, 0)
        self.inteligente = QComboBox()
        self.inteligente.addItem("Todas as tarefas", "todas")
        self.inteligente.addItem("Nenhuma tarefa", "nenhuma")
        self.inteligente.setCurrentIndex(1 if projeto is not None and projeto.inteligente == "nenhuma" else 0)
        grade.addWidget(self.inteligente, 4, 1)
        lay.addLayout(grade)
        lay.addStretch(1)

        botoes = QHBoxLayout()
        botoes.addStretch(1)
        self.btn_ok = QPushButton("Salvar" if projeto is not None else "Adicionar")
        self.btn_ok.setObjectName("ok")
        self.btn_ok.setFixedHeight(34)
        self.btn_ok.setMinimumWidth(100)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_ok.setDefault(True)
        cancelar = QPushButton("Cancelar")
        cancelar.setFixedHeight(34)
        cancelar.clicked.connect(self.reject)
        botoes.addWidget(self.btn_ok)
        botoes.addWidget(cancelar)
        lay.addLayout(botoes)
        raiz.addWidget(esq)

        self.previa = PreviaVisao()
        self.previa.setStyleSheet(f"background: {pal.painel};")
        raiz.addWidget(self.previa, 1)

        self._atualizar_emoji()
        self._atualizar_cores()
        self._atualizar_visao()
        self._validar()
        self.nome.setFocus()

    # ---- partes ----
    def _validar(self):
        self.btn_ok.setEnabled(bool(self.nome.text().strip()))
        pal = tema.atual
        if self.btn_ok.isEnabled():
            self.btn_ok.setStyleSheet(f"QPushButton {{ background: {pal.destaque}; color: white; border: none; "
                                      f"border-radius: 6px; font-weight: 600; }} "
                                      f"QPushButton:hover {{ background: #5a82ff; }}")
        else:
            self.btn_ok.setStyleSheet("QPushButton { background: #2b3a66; color: #7f8cb0; border: none; "
                                      "border-radius: 6px; }")

    def _abrir_emojis(self):
        s = SeletorEmoji(self)
        s.escolhido.connect(self._definir_emoji)
        r = self.btn_emoji.rect()
        s.mostrar_perto(self.btn_emoji.mapToGlobal(r.bottomLeft()))
        s.busca.setFocus()
        self._seletor = s

    def _definir_emoji(self, emoji: str):
        self._emoji = emoji
        self._atualizar_emoji()

    def _atualizar_emoji(self):
        if self._emoji:
            self.btn_emoji.setIcon(QIcon())
            self.btn_emoji.setText(self._emoji)
        else:
            self.btn_emoji.setText("")
            self.btn_emoji.setIcon(icones.icone("lista", tema.atual.apagado, 20))
            self.btn_emoji.setIconSize(QSize(20, 20))

    def _escolher_cor(self, cor: str):
        self._cor = cor
        self._atualizar_cores()

    def _atualizar_cores(self):
        pal = tema.atual
        for cor, b in self.bolinhas:
            ativa = cor == self._cor
            fundo = cor or "transparent"
            borda = pal.texto if ativa else (pal.apagado if not cor else cor)
            b.setStyleSheet(f"QPushButton {{ background: {fundo}; border: {2 if ativa else 1}px solid {borda}; "
                            f"border-radius: 12px; padding: 0; }}")
        self.previa.definir(self._visao, self._cor or pal.destaque)

    def _escolher_visao(self, chave: str):
        self._visao = chave
        self._atualizar_visao()

    def _atualizar_visao(self):
        pal = tema.atual
        for chave, icone, _nome in self.VISOES:
            b = self.btns_visao[chave]
            ativo = chave == self._visao
            b.setChecked(ativo)
            b.setIcon(icones.icone(icone, pal.destaque if ativo else pal.texto_barra, 24))
            b.setStyleSheet(
                f"QPushButton {{ background: {pal.barra_ativa if not ativo else pal.linha_selecionada}; "
                f"border: 2px solid {pal.destaque if ativo else 'transparent'}; border-radius: 8px; }}")
        self.previa.definir(self._visao, self._cor or pal.destaque)

    def _ao_escolher_pasta(self, indice: int):
        if self.pasta.itemData(indice) != "__nova__":
            self._pasta_anterior = indice
            return
        nome, ok = QInputDialog.getText(self, "Nova pasta", "Nome da pasta:")
        nome = nome.strip()
        if ok and nome:
            existente = self.pasta.findData(nome)
            if existente < 0:
                self.pasta.insertItem(self.pasta.count() - 1, nome, nome)
                existente = self.pasta.findData(nome)
            self.pasta.setCurrentIndex(existente)
            self._pasta_anterior = existente
        else:
            self.pasta.setCurrentIndex(self._pasta_anterior)

    def resultado(self) -> dict:
        return {"nome": self.nome.text().strip(), "cor": self._cor or SEM_COR, "emoji": self._emoji, "visao": self._visao,
                "pasta": self.pasta.currentData() if self.pasta.currentData() != "__nova__" else "",
                "tipo": self.tipo.currentData(), "inteligente": self.inteligente.currentData()}
