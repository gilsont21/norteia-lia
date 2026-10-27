"""Leitura e escrita de arquivos .ics (iCalendar), o formato que Google Agenda, Outlook e Apple usam.

Cobre o que um app de tarefas precisa: eventos e tarefas com data, hora, repetição (RRULE) e
alarmes. Não é um parser completo da norma (não trata exceções de repetição, por exemplo).
Horários vindos com fuso são convertidos para o horário local do computador.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from dateutil import tz as _tz
from dateutil.rrule import rrulestr

from .models import Tarefa


@dataclass
class EventoICS:
    uid: str
    titulo: str
    inicio: datetime | date           # date = dia inteiro
    fim: datetime | date | None = None
    descricao: str = ""
    local: str = ""
    regra: str | None = None
    tipo: str = "VEVENT"              # VEVENT ou VTODO
    concluido: bool = False
    lembretes: list[int] = field(default_factory=list)   # minutos antes
    prioridade: int = 0

    @property
    def dia_inteiro(self) -> bool:
        return not isinstance(self.inicio, datetime)

    def dias(self) -> tuple[date, date]:
        """Primeiro e último dia (inclusive) da primeira ocorrência."""
        ini = self.inicio.date() if isinstance(self.inicio, datetime) else self.inicio
        if self.fim is None:
            return ini, ini
        fim = self.fim.date() if isinstance(self.fim, datetime) else self.fim
        if self.dia_inteiro:                      # DTEND de dia inteiro é exclusivo
            fim = fim - timedelta(days=1)
        elif isinstance(self.fim, datetime) and self.fim.time() == time(0, 0) and fim > ini:
            fim = fim - timedelta(days=1)         # terminou à meia-noite: não conta o dia seguinte
        return ini, max(ini, fim)


# ---------- leitura ----------
def _desdobrar(texto: str) -> list[str]:
    linhas: list[str] = []
    for bruta in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if bruta[:1] in (" ", "\t") and linhas:
            linhas[-1] += bruta[1:]
        elif bruta.strip():
            linhas.append(bruta)
    return linhas


def _desescapar(v: str) -> str:
    return (v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",")
            .replace("\\;", ";").replace("\\\\", "\\"))


def _propriedade(linha: str) -> tuple[str, dict[str, str], str]:
    cab, _, valor = linha.partition(":")
    nome, *params = cab.split(";")
    ps = {}
    for p in params:
        k, _, v = p.partition("=")
        ps[k.upper()] = v.strip('"')
    return nome.upper(), ps, valor


def _data(valor: str, params: dict[str, str], destino) -> datetime | date | None:
    valor = valor.strip()
    try:
        if params.get("VALUE") == "DATE" or (len(valor) == 8 and "T" not in valor):
            return datetime.strptime(valor[:8], "%Y%m%d").date()
        if valor.endswith("Z"):
            dt = datetime.strptime(valor, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            return dt.astimezone(destino).replace(tzinfo=None)
        dt = datetime.strptime(valor[:15], "%Y%m%dT%H%M%S")
        zona = _tz.gettz(params["TZID"]) if params.get("TZID") else None
        if zona is not None:
            return dt.replace(tzinfo=zona).astimezone(destino).replace(tzinfo=None)
        return dt                                  # horário "flutuante": vale como está
    except ValueError:
        return None


def _duracao(valor: str) -> timedelta | None:
    m = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", valor.strip())
    if not m:
        return None
    sinal = -1 if m.group(1) == "-" else 1
    sem, d, h, mi, s = (int(x or 0) for x in m.groups()[1:])
    return sinal * timedelta(weeks=sem, days=d, hours=h, minutes=mi, seconds=s)


def _normalizar_regra(regra: str) -> str:
    regra = re.sub(r"UNTIL=(\d{8}T\d{6})Z", r"UNTIL=\1", regra)
    regra = re.sub(r"UNTIL=(\d{8})(?![T\d])", r"UNTIL=\1T235959", regra)
    return regra.removeprefix("RRULE:")


def ler_ics(texto: str, tz_destino=None) -> list[EventoICS]:
    destino = tz_destino or _tz.tzlocal()
    eventos: list[EventoICS] = []
    atual: dict | None = None
    alarme: dict | None = None
    for linha in _desdobrar(texto):
        nome, params, valor = _propriedade(linha)
        if nome == "BEGIN" and valor in ("VEVENT", "VTODO"):
            atual = {"tipo": valor, "lembretes": []}
        elif nome == "BEGIN" and valor == "VALARM" and atual is not None:
            alarme = {}
        elif nome == "END" and valor == "VALARM":
            if atual is not None and alarme and "gatilho" in alarme:
                minutos = int(-alarme["gatilho"].total_seconds() // 60)
                if minutos >= 0:
                    atual["lembretes"].append(minutos)
            alarme = None
        elif nome == "END" and valor in ("VEVENT", "VTODO") and atual is not None:
            ev = _montar(atual)
            if ev is not None:
                eventos.append(ev)
            atual = None
        elif atual is not None and alarme is not None:
            if nome == "TRIGGER" and params.get("RELATED", "START") == "START":
                d = _duracao(valor)
                if d is not None:
                    alarme["gatilho"] = d
        elif atual is not None:
            if nome in ("DTSTART", "DTEND", "DUE"):
                atual[nome.lower()] = _data(valor, params, destino)
            elif nome == "DURATION":
                atual["duracao"] = _duracao(valor)
            elif nome == "SUMMARY":
                atual["titulo"] = _desescapar(valor)
            elif nome == "DESCRIPTION":
                atual["descricao"] = _desescapar(valor)
            elif nome == "LOCATION":
                atual["local"] = _desescapar(valor)
            elif nome == "UID":
                atual["uid"] = valor.strip()
            elif nome == "RRULE":
                atual["regra"] = _normalizar_regra(valor)
            elif nome == "STATUS":
                atual["status"] = valor.strip().upper()
            elif nome == "PRIORITY":
                atual["prioridade"] = int(valor) if valor.strip().isdigit() else 0
            elif nome == "COMPLETED":
                atual["completed"] = True
    return eventos


def _montar(d: dict) -> EventoICS | None:
    inicio = d.get("dtstart") or d.get("due")
    if inicio is None:
        return None
    fim = d.get("dtend") if d["tipo"] == "VEVENT" else None
    if fim is None and d.get("duracao") is not None:
        fim = inicio + d["duracao"]
    # prioridade do iCalendar: 1-4 alta, 5 média, 6-9 baixa (0 = nenhuma)
    p = d.get("prioridade", 0)
    prioridade = 0 if p == 0 else 3 if p <= 4 else 2 if p == 5 else 1
    return EventoICS(
        uid=d.get("uid", ""), titulo=d.get("titulo", "(sem título)"), inicio=inicio, fim=fim,
        descricao=d.get("descricao", ""), local=d.get("local", ""), regra=d.get("regra"),
        tipo=d["tipo"], concluido=d.get("status") == "COMPLETED" or d.get("completed", False),
        lembretes=sorted(set(d["lembretes"])), prioridade=prioridade)


def ocorrencias_do_evento(ev: EventoICS, ini: date, fim: date, limite: int = 500) -> list[tuple[date, date]]:
    """[(primeiro dia, último dia)] de cada ocorrência que encosta no período [ini, fim]."""
    p, u = ev.dias()
    duracao = (u - p).days
    if not ev.regra:
        return [(p, u)] if p <= fim and u >= ini else []
    base = ev.inicio if isinstance(ev.inicio, datetime) else datetime.combine(ev.inicio, time(0, 0))
    try:
        regra = rrulestr(ev.regra, dtstart=base)
    except (ValueError, KeyError):
        return [(p, u)] if p <= fim and u >= ini else []
    janela_ini = datetime.combine(ini - timedelta(days=duracao), time(0, 0))
    janela_fim = datetime.combine(fim, time(23, 59, 59))
    saida: list[tuple[date, date]] = []
    for ocorrencia in regra.between(janela_ini, janela_fim, inc=True):
        d0 = ocorrencia.date()
        saida.append((d0, d0 + timedelta(days=duracao)))
        if len(saida) >= limite:
            break
    return saida


# ---------- escrita ----------
def _escapar(v: str) -> str:
    return v.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _dobrar(linha: str) -> str:
    """Linhas do iCalendar têm no máximo 75 bytes; o excesso continua na linha seguinte, com um espaço."""
    dados = linha.encode("utf-8")
    if len(dados) <= 75:
        return linha
    partes, atual = [], b""
    for ch in linha:
        b = ch.encode("utf-8")
        limite = 75 if not partes else 74
        if len(atual) + len(b) > limite:
            partes.append(atual.decode("utf-8"))
            atual = b""
        atual += b
    partes.append(atual.decode("utf-8"))
    return "\r\n ".join(partes)


def _utc(dt: datetime, zona) -> str:
    return dt.replace(tzinfo=zona).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def escrever_ics(tarefas: list[Tarefa], nome: str = "Tarefas", agora: datetime | None = None,
                 tz_origem=None, duracao_padrao: int = 60) -> str:
    zona = tz_origem or _tz.tzlocal()
    carimbo = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    linhas = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Tarefas//PT-BR//", "CALSCALE:GREGORIAN",
              f"X-WR-CALNAME:{_escapar(nome)}"]
    for t in tarefas:
        if t.prazo is None:
            continue
        inicio_dia = t.inicio or t.prazo
        linhas += ["BEGIN:VEVENT", f"UID:{t.uuid}@tarefas", f"DTSTAMP:{carimbo}",
                   f"SUMMARY:{_escapar(('✓ ' if t.concluida else '') + t.titulo)}"]
        if t.prazo_hora is None:
            linhas.append("DTSTART;VALUE=DATE:" + inicio_dia.strftime("%Y%m%d"))
            linhas.append("DTEND;VALUE=DATE:" + (t.prazo + timedelta(days=1)).strftime("%Y%m%d"))
        else:
            fim_dt = datetime.combine(t.prazo, t.prazo_hora)
            ini_dt = (datetime.combine(inicio_dia, t.prazo_hora) if t.inicio
                      else fim_dt)
            fim_real = fim_dt + timedelta(minutes=t.duracao_min or duracao_padrao)
            linhas.append("DTSTART:" + _utc(ini_dt, zona))
            linhas.append("DTEND:" + _utc(fim_real, zona))
        if t.notas:
            linhas.append(f"DESCRIPTION:{_escapar(t.notas)}")
        if t.repeticao:
            linhas.append(f"RRULE:{t.repeticao}")
        if t.tags:
            linhas.append("CATEGORIES:" + ",".join(_escapar(g) for g in t.tags))
        if t.prioridade:
            linhas.append("PRIORITY:" + str({3: 1, 2: 5, 1: 9}[int(t.prioridade)]))
        for minutos in t.lembretes:
            linhas += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_escapar(t.titulo)}",
                       f"TRIGGER:-PT{int(minutos)}M", "END:VALARM"]
        linhas.append("END:VEVENT")
    linhas.append("END:VCALENDAR")
    return "\r\n".join(_dobrar(l) for l in linhas) + "\r\n"
