"""Pequenas ajudas de desenho e de texto usadas pelas várias telas."""
from __future__ import annotations

from datetime import date, datetime

from PySide6.QtGui import QColor

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]
DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
DIAS_CURTOS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]       # índice = date.weekday()
INICIAIS = ["S", "T", "Q", "Q", "S", "S", "D"]


def com_alfa(cor: str, alfa: int) -> QColor:
    c = QColor(cor)
    c.setAlpha(alfa)
    return c


def mais_escuro(cor: str, fator: int = 130) -> QColor:
    return QColor(cor).darker(fator)


def texto_sobre(cor: str) -> QColor:
    """Branco ou preto, o que ler melhor sobre a cor."""
    c = QColor(cor)
    luz = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return QColor("#101010") if luz > 170 else QColor("#ffffff")


def nome_do_mes(d: date) -> str:
    return f"{MESES[d.month - 1]} de {d.year}"


def dia_por_extenso(d: date) -> str:
    return f"{DIAS_SEMANA[d.weekday()]}, {d.day} de {MESES[d.month - 1]} de {d.year}"


def intervalo_por_extenso(ini: date, fim: date) -> str:
    if ini.year == fim.year and ini.month == fim.month:
        return f"{ini.day} – {fim.day} de {MESES[ini.month - 1]} de {ini.year}"
    if ini.year == fim.year:
        return f"{ini.day} de {MESES[ini.month - 1][:3]} – {fim.day} de {MESES[fim.month - 1][:3]} de {ini.year}"
    return f"{ini.day}/{ini.month}/{ini.year} – {fim.day}/{fim.month}/{fim.year}"


def hora_texto(h) -> str:
    return h.strftime("%H:%M")


# ---------- rótulo do prazo (o "chip" de data dos cartões) ----------
def _dia_curto(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1][:3]}"


def rotulo_prazo(prazo: date | None, hora=None, duracao_min: int = 0, inicio: date | None = None,
                 repete: bool = False, hoje: date | None = None) -> tuple[str, str]:
    """Texto do chip de data e o "tom" dele: "atrasado", "hoje" ou "normal".

    Exemplos: "25 de out, Hoje"; "26 de out, Amanhã, 17:00 - 18:00"; "4 de out, 21d atrasado"; "Data"."""
    hoje = hoje or date.today()
    if prazo is None:
        return "Data", "vazio"
    texto = _dia_curto(prazo)
    if inicio is not None and inicio != prazo:
        texto = f"{_dia_curto(inicio)} - {_dia_curto(prazo)}"
    delta = (prazo - hoje).days
    if delta == 0:
        texto += ", Hoje"
    elif delta == 1:
        texto += ", Amanhã"
    elif delta == -1:
        texto += ", Ontem"
    elif 2 <= delta <= 6:
        texto += f", {DIAS_CURTOS[prazo.weekday()]}"
    elif 7 <= delta <= 13:
        texto += f", Próxima {DIAS_CURTOS[prazo.weekday()]}"
    if hora is not None:
        h = hora.strftime("%H:%M")
        if duracao_min:
            total = hora.hour * 60 + hora.minute + duracao_min
            fim = f"{min(total, 24 * 60 - 1) // 60:02d}:{min(total, 24 * 60 - 1) % 60:02d}"
            texto += f", {h} - {fim}"
        else:
            texto += f", {h}"
    atrasado = delta < 0 or (delta == 0 and hora is not None and datetime.now().time() > hora)
    if delta < 0:
        texto = texto.replace(", Ontem", "") + f", {-delta}d atrasado"
    if repete:
        texto += " ↻"
    tom = "atrasado" if atrasado else ("hoje" if delta == 0 else "normal")
    return texto, tom
