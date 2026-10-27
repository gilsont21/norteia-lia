from __future__ import annotations

from datetime import date, time, timedelta

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MESES_LONGOS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
                "setembro", "outubro", "novembro", "dezembro"]
DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
DIAS_LONGOS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira",
               "sábado", "domingo"]


def rotulo_prazo(d: date | None, hoje: date | None = None) -> str:
    if d is None:
        return ""
    hoje = hoje or date.today()
    if d == hoje:
        return "Hoje"
    if d == hoje + timedelta(days=1):
        return "Amanhã"
    if d == hoje - timedelta(days=1):
        return "Ontem"
    if 0 < (d - hoje).days < 7:
        return DIAS_LONGOS[d.weekday()].split("-")[0].capitalize()
    if d.year == hoje.year:
        return f"{d.day} de {MESES[d.month - 1]}"
    return d.strftime("%d/%m/%Y")


def rotulo_com_hora(d: date | None, hora: time | None, repete: bool = False,
                    hoje: date | None = None) -> str:
    """'Hoje 14:30 ↻' — data, hora (se houver) e marca de repetição."""
    texto = rotulo_prazo(d, hoje)
    if texto and hora:
        texto += f" {hora.strftime('%H:%M')}"
    if texto and repete:
        texto += " ↻"
    return texto


def data_por_extenso(d: date) -> str:
    return f"{DIAS_LONGOS[d.weekday()]}, {d.day} de {MESES_LONGOS[d.month - 1]}"
