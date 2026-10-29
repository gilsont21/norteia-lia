"""Paletas e folha de estilo. Cada cor de destaque existe em modo claro e escuro, e o modo pode seguir o sistema.

Para criar uma cor nova, acrescente uma linha em `CORES`. A paleta inteira sai de lá.
As preferências ficam em três chaves: `tema_cor`, `tema_modo` ("claro", "escuro" ou "sistema") e `tema_fundo`.
"""
from __future__ import annotations

import colorsys
import re
import tempfile
from dataclasses import dataclass, fields
from pathlib import Path

NOME_PRIORIDADE = {0: "Nenhuma", 1: "Baixa", 2: "Média", 3: "Alta"}
FONTE = "'Segoe UI', Inter, 'DejaVu Sans', sans-serif"
_ASSETS = Path(__file__).parent / "assets"

COR_PADRAO = "padrao"
MODO_PADRAO = "escuro"
MODOS = [("claro", "Claro"), ("escuro", "Escuro"), ("sistema", "Seguir o sistema")]


@dataclass(frozen=True)
class Paleta:
    nome: str
    escuro: bool
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
    borda: str          # separadores (e trilhas de gráficos)
    destaque: str       # cor de destaque
    destaque_hover: str
    sobre_destaque: str
    linha_selecionada: str
    linha_hover: str
    vermelho: str
    prioridade: tuple   # nenhuma, baixa, média, alta
    sutil: str          # ícones desligados, pontos vazios
    caixa: str          # borda das caixinhas de conclusão
    barra_rolagem: str
    seta: str           # arquivo svg da seta dos seletores
    seta_cima: str      # arquivo svg da seta para cima (caixas numéricas)
    marca: str          # arquivo svg do "certo" das caixinhas marcadas


@dataclass(frozen=True)
class CorTema:
    chave: str
    nome: str
    matiz: float | None       # 0 a 360; None = cinza neutro
    tinta: float              # quanto o fundo puxa para a cor (0 a 1)
    acento_escuro: str
    acento_claro: str


CORES = [
    CorTema("padrao", "Padrão", None, 0.0, "#4772fa", "#3b63e8"),
    CorTema("ceu", "Céu", 214, 0.34, "#4a9cf0", "#2677d6"),
    CorTema("turquesa", "Turquesa", 166, 0.30, "#2fc9a8", "#0c9a7f"),
    CorTema("oceano", "Oceano", 190, 0.32, "#35b8d0", "#0b8aa0"),
    CorTema("campo", "Campo", 100, 0.26, "#8cc63f", "#4f8f1c"),
    CorTema("ambar", "Âmbar", 38, 0.34, "#f9b233", "#c26d00"),
    CorTema("rosa", "Rosa", 346, 0.30, "#f0607f", "#d02d57"),
    CorTema("lilas", "Lilás", 262, 0.30, "#a58af5", "#7048d8"),
    CorTema("ebano", "Ébano", 24, 0.30, "#cf9870", "#96592a"),
    CorTema("grafite", "Grafite", 218, 0.16, "#8ea4cf", "#4c6296"),
]
POR_CHAVE = {c.chave: c for c in CORES}


def _hex(r: float, g: float, b: float) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(v * 255))) for v in (r, g, b)))


def _tom(matiz: float | None, luz: float, sat: float) -> str:
    if matiz is None:
        sat = 0.0
    return _hex(*colorsys.hls_to_rgb((matiz or 0) / 360.0, luz, sat))


def _misturar(a: str, b: str, parte: float) -> str:
    """`parte` de `a` misturada em `b` (0 = só b, 1 = só a)."""
    ra, rb = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#{:02x}{:02x}{:02x}".format(*(round(x * parte + y * (1 - parte)) for x, y in zip(ra, rb)))


def _luz_relativa(cor: str) -> float:
    def canal(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(int(cor[i:i + 2], 16)) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    la, lb = sorted((_luz_relativa(a), _luz_relativa(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _escurecer_para_texto(cor: str) -> str:
    """Cor de texto que fica legível sobre `cor` (preto ou branco)."""
    return "#ffffff" if contraste(cor, "#ffffff") >= contraste(cor, "#101114") else "#101114"


def arquivos_de_marcas(cor: str, cor_marca: str) -> tuple[str, str, str]:
    """Cria (se preciso) as setas e o "certo" em SVG nas cores pedidas e devolve os caminhos."""
    pasta = Path(tempfile.gettempdir()) / "norteia-tema"
    try:
        pasta.mkdir(exist_ok=True)
        certo = pasta / f"certo-{cor_marca[1:]}.svg"
        if not certo.exists():
            certo.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
                             f'<path d="M4 8.5 L7 11.5 L12 5" fill="none" stroke="{cor_marca}" stroke-width="2" '
                             'stroke-linecap="round" stroke-linejoin="round"/></svg>', encoding="utf-8")
        baixo = pasta / f"seta-{cor[1:]}.svg"
        cima = pasta / f"seta-cima-{cor[1:]}.svg"
        if not baixo.exists():
            baixo.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
                             f'<path d="M2.5 4.5 L6 8 L9.5 4.5" fill="none" stroke="{cor}" stroke-width="1.6" '
                             'stroke-linecap="round" stroke-linejoin="round"/></svg>', encoding="utf-8")
        if not cima.exists():
            cima.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
                            f'<path d="M2.5 7.5 L6 4 L9.5 7.5" fill="none" stroke="{cor}" stroke-width="1.6" '
                            'stroke-linecap="round" stroke-linejoin="round"/></svg>', encoding="utf-8")
        return baixo.as_posix(), cima.as_posix(), certo.as_posix()
    except OSError:
        return ((_ASSETS / "seta-escuro.svg").as_posix(), (_ASSETS / "seta-cima-escuro.svg").as_posix(),
                (_ASSETS / "check.svg").as_posix())


def paleta(cor: str = COR_PADRAO, escuro: bool = True) -> Paleta:
    t = POR_CHAVE.get(cor) or POR_CHAVE[COR_PADRAO]
    nome = f"{t.chave}-{'escuro' if escuro else 'claro'}"
    if t.chave == COR_PADRAO and escuro:       # o visual original, byte a byte
        return Paleta(
            nome=nome, escuro=True, fundo="#1c1c1c", barra="#212121", trilho="#181818", painel="#1c1c1c",
            campo="#272727", barra_ativa="#2d2d2d", barra_hover="#262626", texto="#e8e8e8", texto_barra="#dcdcdc",
            apagado="#8c8c8c", borda="#2c2c2c", destaque="#4772fa", destaque_hover="#5a82ff", sobre_destaque="#ffffff",
            linha_selecionada="#262c3d", linha_hover="#232323", vermelho="#f0524a",
            prioridade=("#7a7a7a", "#4772fa", "#f5a623", "#f0524a"), sutil="#4d4d4d", caixa="#5c5c5c",
            barra_rolagem="#3a3a3a", seta=(_ASSETS / "seta-escuro.svg").as_posix(),
            seta_cima=(_ASSETS / "seta-cima-escuro.svg").as_posix(), marca=(_ASSETS / "check.svg").as_posix())
    if t.chave == COR_PADRAO:                  # claro neutro
        fundo, barra, trilho, campo = "#fcfcfd", "#f3f4f7", "#e9ebf0", "#eef0f4"
        ativa, hover, borda = "#e1e4eb", "#e8eaf0", "#e1e4ea"
        texto, texto_barra, apagado = "#1f2328", "#2b3036", "#6b7280"
        sutil, caixa, rolagem, l_hover = "#b9bec8", "#98a0ad", "#c9cdd5", "#f0f2f6"
        nenhuma = "#9aa0ab"
    else:
        h, s = t.matiz, t.tinta
        if escuro:
            fundo, barra, trilho = _tom(h, .105, s * .45), _tom(h, .128, s * .45), _tom(h, .085, s * .45)
            campo, ativa, hover = _tom(h, .155, s * .42), _tom(h, .185, s * .42), _tom(h, .150, s * .42)
            borda, l_hover = _tom(h, .175, s * .40), _tom(h, .135, s * .45)
            texto, texto_barra, apagado = "#e8e8e8", "#dcdcdc", _tom(h, .60, s * .30)
            sutil, caixa, rolagem = _tom(h, .31, s * .30), _tom(h, .40, s * .30), _tom(h, .25, s * .35)
            nenhuma = _tom(h, .50, s * .20)
        else:
            fundo, barra, trilho = _tom(h, .985, s * .9), _tom(h, .958, s * .85), _tom(h, .925, s * .80)
            campo, ativa, hover = _tom(h, .940, s * .80), _tom(h, .895, s * .75), _tom(h, .920, s * .75)
            borda, l_hover = _tom(h, .900, s * .70), _tom(h, .950, s * .80)
            texto, texto_barra, apagado = _tom(h, .13, s * .30), _tom(h, .17, s * .30), _tom(h, .42, s * .20)
            sutil, caixa, rolagem = _tom(h, .76, s * .30), _tom(h, .62, s * .25), _tom(h, .79, s * .35)
            nenhuma = _tom(h, .62, s * .20)
    destaque = t.acento_escuro if escuro else t.acento_claro
    vermelho = "#f0524a" if escuro else "#d9362e"
    amarelo = "#f5a623" if escuro else "#c97f0a"
    sobre = _escurecer_para_texto(destaque)
    seta, seta_cima, marca = arquivos_de_marcas(apagado, sobre)
    return Paleta(
        nome=nome, escuro=escuro, fundo=fundo, barra=barra, trilho=trilho, painel=fundo, campo=campo,
        barra_ativa=ativa, barra_hover=hover, texto=texto, texto_barra=texto_barra, apagado=apagado, borda=borda,
        destaque=destaque, destaque_hover=_misturar("#ffffff", destaque, 0.14) if escuro else _misturar("#000000", destaque, 0.12),
        sobre_destaque=sobre,
        linha_selecionada=_misturar(destaque, fundo, 0.16 if escuro else 0.12), linha_hover=l_hover,
        vermelho=vermelho, prioridade=(nenhuma, destaque, amarelo, vermelho), sutil=sutil, caixa=caixa,
        barra_rolagem=rolagem, seta=seta, seta_cima=seta_cima, marca=marca)


atual: Paleta = paleta(COR_PADRAO, True)


def definir(cor: str = COR_PADRAO, escuro: bool = True) -> Paleta:
    global atual
    atual = paleta(cor, escuro)
    return atual


def escuro_do_sistema() -> bool:
    """True se o sistema está no modo escuro (ou se não dá para saber)."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        esquema = QGuiApplication.styleHints().colorScheme()
        return esquema != Qt.ColorScheme.Light
    except Exception:
        return True


def modo_escuro(modo: str) -> bool:
    if modo == "claro":
        return False
    if modo == "sistema":
        return escuro_do_sistema()
    return True


def da_preferencia(prefs: dict) -> Paleta:
    cor = prefs.get("tema_cor") or COR_PADRAO
    if cor not in POR_CHAVE:
        cor = COR_PADRAO
    return definir(cor, modo_escuro(prefs.get("tema_modo") or MODO_PADRAO))


# ---- troca ao vivo: o mesmo texto de estilo, com as cores antigas trocadas pelas novas ----
def mapa_de_cores(antiga: Paleta, nova: Paleta) -> dict[str, str]:
    saida: dict[str, str] = {}
    for campo in fields(Paleta):
        if campo.name in ("nome", "escuro"):
            continue
        a, n = getattr(antiga, campo.name), getattr(nova, campo.name)
        pares = zip(a, n) if isinstance(a, tuple) else [(a, n)]
        for x, y in pares:
            if x.lower() != y.lower():
                saida.setdefault(x.lower(), y)
    return saida


def trocar_cores(texto: str, mapa: dict[str, str]) -> str:
    if not mapa or not texto:
        return texto
    padrao = re.compile("|".join(re.escape(k) for k in sorted(mapa, key=len, reverse=True)), re.IGNORECASE)
    return padrao.sub(lambda m: mapa[m.group(0).lower()], texto)


def qss() -> str:
    p = atual
    check = p.marca
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
QScrollBar::handle:vertical {{ background: {p.barra_rolagem}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 10px; background: transparent; }}
QScrollBar::handle:horizontal {{ background: {p.barra_rolagem}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""
