"""Paleta e folha de estilo: um único tema escuro, cinza neutro com destaque azul.

Para mudar o visual, mexa só na paleta `ESCURO` abaixo.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

NOME_PRIORIDADE = {0: "Nenhuma", 1: "Baixa", 2: "Média", 3: "Alta"}
FONTE = "'Segoe UI', Inter, 'DejaVu Sans', sans-serif"
_ASSETS = Path(__file__).parent / "assets"


@dataclass(frozen=True)
class Paleta:
    nome: str
    fundo: str          # área central
    barra: str          # barra lateral
    trilho: str         # coluna fina de ícones
    painel: str         # painel de detalhe
    campo: str          # campos de entrada
    barra_ativa: str
    barra_hover: str
    texto: str
    texto_barra: str
    apagado: str
    borda: str          # separadores
    destaque: str       # azul de destaque
    sobre_destaque: str
    linha_selecionada: str
    linha_hover: str
    vermelho: str
    prioridade: tuple   # nenhuma, baixa, média, alta
    seta: str           # arquivo svg da seta dos seletores
    seta_cima: str      # arquivo svg da seta para cima (caixas numéricas)


ESCURO = Paleta(
    nome="escuro",
    fundo="#1c1c1c", barra="#212121", trilho="#181818", painel="#1c1c1c", campo="#272727",
    barra_ativa="#2d2d2d", barra_hover="#262626",
    texto="#e8e8e8", texto_barra="#dcdcdc", apagado="#8c8c8c", borda="#2c2c2c",
    destaque="#4772fa", sobre_destaque="#ffffff",
    linha_selecionada="#262c3d", linha_hover="#232323",
    vermelho="#f0524a",
    prioridade=("#7a7a7a", "#4772fa", "#f5a623", "#f0524a"),
    seta=(_ASSETS / "seta-escuro.svg").as_posix(),
    seta_cima=(_ASSETS / "seta-cima-escuro.svg").as_posix(),
)

atual: Paleta = ESCURO


def qss() -> str:
    p = atual
    check = (_ASSETS / "check.svg").as_posix()
    return f"""
* {{ font-family: {FONTE}; color: {p.texto}; }}
QMainWindow, QWidget#raiz {{ background: {p.fundo}; }}
QWidget#centro {{ background: {p.fundo}; }}
QWidget#barra {{ background: {p.barra}; }}
QWidget#trilho {{ background: {p.trilho}; }}
QPushButton#btnTrilho {{ background: transparent; border: none; border-radius: 8px; padding: 0; }}
QPushButton#btnTrilho:hover {{ background: {p.barra_hover}; }}
QPushButton#btnTrilho:checked {{ background: {p.barra_ativa}; }}
QPushButton#btnTrilho:disabled {{ background: transparent; }}
QPushButton#btnIcone {{ background: transparent; border: none; border-radius: 6px; padding: 0; }}
QPushButton#btnIcone:hover {{ background: {p.barra_hover}; }}
QPushButton#btnBarra {{
    background: transparent; border: none; color: {p.apagado}; text-align: left;
    padding: 10px 20px; font-size: 13px; border-radius: 0;
}}
QPushButton#btnBarra:hover {{ color: {p.texto}; background: transparent; border: none; }}
QLabel#mensagemVazia {{ color: {p.apagado}; font-size: 14px; }}
QWidget#detalhe {{ background: {p.painel}; border-left: 1px solid {p.borda}; }}
QLabel#titulo {{ font-size: 22px; font-weight: 700; }}
QLabel#secao {{ font-size: 11px; font-weight: 600; color: {p.apagado}; }}
QLineEdit#entrada {{
    background: {p.campo}; border: 1px solid transparent; border-radius: 6px;
    padding: 11px 14px 11px 38px; font-size: 14px; selection-background-color: {p.destaque};
    selection-color: {p.sobre_destaque};
}}
QLineEdit#entrada:focus {{ border: 1px solid {p.destaque}; }}
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget#tarefas::item {{ border: none; }}
QWidget#detalhe QLineEdit, QWidget#detalhe QPlainTextEdit, QWidget#detalhe QComboBox,
QWidget#detalhe QDateTimeEdit {{
    background: {p.campo}; border: 1px solid transparent; border-radius: 6px; padding: 8px 10px;
    font-size: 13px; selection-background-color: {p.destaque}; selection-color: {p.sobre_destaque};
}}
QWidget#detalhe QLineEdit:focus, QWidget#detalhe QPlainTextEdit:focus,
QWidget#detalhe QDateTimeEdit:focus, QWidget#detalhe QComboBox:focus {{
    border: 1px solid {p.destaque};
}}
QWidget#detalhe QLineEdit#tituloTarefa {{
    font-size: 17px; font-weight: 600; background: transparent; padding: 6px 4px;
    border: 1px solid transparent;
}}
QWidget#detalhe QLineEdit#tituloTarefa:focus {{ background: {p.campo}; border: 1px solid {p.destaque}; }}
QPlainTextEdit#campoIA {{
    background: {p.campo}; border: 1px solid {p.borda}; border-radius: 8px; padding: 6px 8px; font-size: 13px;
    selection-background-color: {p.destaque}; selection-color: {p.sobre_destaque};
}}
QPlainTextEdit#campoIA:focus {{ border: 1px solid {p.destaque}; }}
QComboBox, QDateEdit, QTimeEdit, QSpinBox, QDateTimeEdit {{
    background: {p.campo}; border: 1px solid {p.borda}; border-radius: 6px; padding: 6px 10px;
    font-size: 13px; selection-background-color: {p.destaque}; selection-color: {p.sobre_destaque};
}}
QComboBox:focus, QDateEdit:focus, QTimeEdit:focus, QSpinBox:focus {{ border: 1px solid {p.destaque}; }}
QComboBox:disabled, QDateEdit:disabled, QTimeEdit:disabled, QSpinBox:disabled {{ color: {p.apagado}; }}
QTimeEdit {{ padding-left: 14px; }}
QTimeEdit::up-button, QTimeEdit::down-button {{ width: 0px; height: 0px; border: none; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; border: none; background: transparent; }}
QSpinBox::up-arrow {{ image: url({p.seta_cima}); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url({p.seta}); width: 10px; height: 10px; }}
QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url({p.seta}); width: 12px; height: 12px; }}
QRadioButton {{ font-size: 13px; spacing: 8px; }}
QComboBox QAbstractItemView {{
    background: {p.campo}; border: 1px solid {p.borda}; outline: none; padding: 4px;
    selection-background-color: {p.barra_ativa}; selection-color: {p.texto};
}}
QCalendarWidget QWidget {{ background: {p.campo}; color: {p.texto}; }}
QCalendarWidget QToolButton {{ background: transparent; color: {p.texto}; padding: 4px 8px; }}
QCalendarWidget QAbstractItemView {{
    background: {p.campo}; color: {p.texto}; selection-background-color: {p.destaque};
    selection-color: {p.sobre_destaque}; outline: none;
}}
QCalendarWidget QAbstractItemView:disabled {{ color: {p.apagado}; }}
QMenu {{ background: {p.campo}; border: 1px solid {p.borda}; padding: 6px; border-radius: 8px; }}
QMenu::item {{ padding: 7px 22px 7px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: {p.barra_ativa}; }}
QFrame#aviso {{
    background: {p.barra_ativa}; border: 1px solid {p.borda}; border-radius: 12px;
}}
QLabel#avisoTitulo {{ font-size: 15px; font-weight: 600; background: transparent; }}
QLabel#avisoTexto {{ font-size: 13px; color: {p.apagado}; background: transparent; }}
QToolTip {{ background: {p.campo}; color: {p.texto}; border: 1px solid {p.borda}; padding: 4px 6px; }}
QDialog, QMessageBox {{ background: {p.barra}; }}
QDialog QLineEdit {{
    background: {p.campo}; border: 1px solid {p.borda}; border-radius: 6px; padding: 8px 10px;
}}
QPushButton {{
    background: {p.campo}; border: 1px solid {p.borda}; border-radius: 6px;
    padding: 8px 14px; font-size: 13px;
}}
QPushButton:hover {{ border: 1px solid {p.destaque}; }}
QPushButton:disabled {{ color: {p.apagado}; }}
QPushButton#perigo {{ color: {p.vermelho}; }}
QPushButton::menu-indicator {{ image: none; width: 0px; }}
QCheckBox {{ font-size: 13px; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px; border: 1px solid {p.apagado};
    background: {p.campo};
}}
QCheckBox::indicator:checked {{ background: {p.destaque}; border: 1px solid {p.destaque}; image: url({check}); }}
QScrollBar:vertical {{ width: 10px; background: transparent; }}
QScrollBar::handle:vertical {{ background: #3a3a3a; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 10px; background: transparent; }}
QScrollBar::handle:horizontal {{ background: #3a3a3a; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""
