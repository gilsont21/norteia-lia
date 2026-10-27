"""Regras de repetição (subconjunto do formato RRULE, o mesmo do Google Agenda)."""
from __future__ import annotations

from datetime import date, datetime, time

from dateutil.rrule import rrulestr

DIAS_UTEIS = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"

# (texto exibido, regra). A primeira opção é "não repete".
PRESETS: list[tuple[str, str | None]] = [
    ("Não repete", None),
    ("Todo dia", "FREQ=DAILY"),
    ("Dias úteis", DIAS_UTEIS),
    ("Toda semana", "FREQ=WEEKLY"),
    ("Todo mês", "FREQ=MONTHLY"),
    ("Todo ano", "FREQ=YEARLY"),
]

_NOMES_DIAS = {"MO": "seg", "TU": "ter", "WE": "qua", "TH": "qui", "FR": "sex", "SA": "sáb", "SU": "dom"}
_UNIDADE = {"DAILY": ("dia", "dias"), "WEEKLY": ("semana", "semanas"),
            "MONTHLY": ("mês", "meses"), "YEARLY": ("ano", "anos")}


def _partes(regra: str) -> dict[str, str]:
    return dict(p.split("=", 1) for p in regra.split(";") if "=" in p)


def valida(regra: str | None) -> bool:
    if not regra:
        return False
    try:
        rrulestr(regra, dtstart=datetime(2026, 1, 1))
        return True
    except (ValueError, KeyError):
        return False


def proxima(regra: str, prazo: date, hoje: date | None = None) -> date | None:
    """Próxima data da tarefa depois de concluí-la.

    Pega a primeira ocorrência depois do prazo atual e, se a tarefa foi concluída
    com atraso, depois de hoje (não faz sentido criar uma tarefa já vencida).
    """
    hoje = hoje or date.today()
    marco = max(prazo, hoje)
    r = rrulestr(regra, dtstart=datetime.combine(prazo, time(0, 0)))
    seguinte = r.after(datetime.combine(marco, time(23, 59, 59)), inc=False)
    return seguinte.date() if seguinte else None


def descrever(regra: str | None) -> str:
    if not regra:
        return "Não repete"
    for nome, r in PRESETS:
        if r == regra:
            return nome
    p = _partes(regra)
    unidade = _UNIDADE.get(p.get("FREQ", ""))
    if not unidade:
        return "Repetição personalizada"
    n = int(p.get("INTERVAL", "1"))
    texto = f"A cada {unidade[0]}" if n == 1 else f"A cada {n} {unidade[1]}"
    if "BYDAY" in p:
        texto += " (" + ", ".join(_NOMES_DIAS.get(d, d) for d in p["BYDAY"].split(",")) + ")"
    if "COUNT" in p:
        texto += f", {p['COUNT']} vez" + ("" if p["COUNT"] == "1" else "es")
    if "UNTIL" in p:
        try:
            texto += f", até {datetime.strptime(p['UNTIL'][:8], '%Y%m%d'):%d/%m/%Y}"
        except ValueError:
            pass
    return texto


DIAS_RRULE = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]          # índice = date.weekday()
FREQUENCIAS = {"DAILY": "dias", "WEEKLY": "semanas", "MONTHLY": "meses", "YEARLY": "anos"}


def construir(freq: str, intervalo: int = 1, dias: list[int] | None = None,
              ate: date | None = None, vezes: int | None = None) -> str:
    """Monta a regra a partir das escolhas da janela "Personalizar".

    `dias` são dias da semana (0 = segunda) e só valem para repetição semanal. `ate` e `vezes` não se misturam
    (se vierem os dois, vale a data)."""
    if freq not in FREQUENCIAS:
        raise ValueError(f"frequência desconhecida: {freq!r}")
    partes = [f"FREQ={freq}"]
    if intervalo > 1:
        partes.append(f"INTERVAL={int(intervalo)}")
    if freq == "WEEKLY" and dias:
        partes.append("BYDAY=" + ",".join(DIAS_RRULE[d] for d in sorted(set(dias))))
    if ate is not None:
        partes.append("UNTIL=" + ate.strftime("%Y%m%d") + "T235959")
    elif vezes:
        partes.append(f"COUNT={int(vezes)}")
    return ";".join(partes)


_CHAVES_SUPORTADAS = {"FREQ", "INTERVAL", "BYDAY", "UNTIL", "COUNT"}


def analisar(regra: str | None) -> dict | None:
    """Inverso de `construir`. Devolve None se a regra usa algo que a janela não sabe mostrar."""
    if not regra or not valida(regra):
        return None
    p = _partes(regra)
    if set(p) - _CHAVES_SUPORTADAS or p.get("FREQ") not in FREQUENCIAS:
        return None
    dias = []
    if "BYDAY" in p:
        try:
            dias = [DIAS_RRULE.index(d) for d in p["BYDAY"].split(",")]
        except ValueError:
            return None                       # ex.: "1MO" (primeira segunda do mês)
    ate = None
    if "UNTIL" in p:
        try:
            ate = datetime.strptime(p["UNTIL"][:8], "%Y%m%d").date()
        except ValueError:
            return None
    return {"freq": p["FREQ"], "intervalo": int(p.get("INTERVAL", "1")), "dias": dias, "ate": ate,
            "vezes": int(p["COUNT"]) if "COUNT" in p else None}


def decrementar_contagem(regra: str) -> str | None:
    """Regra para a próxima ocorrência quando a repetição tem COUNT (restam N-1). None se era a última."""
    p = _partes(regra)
    if "COUNT" not in p:
        return regra
    n = int(p["COUNT"])
    if n <= 1:
        return None
    return ";".join(f"COUNT={n - 1}" if x.startswith("COUNT=") else x for x in regra.split(";"))
