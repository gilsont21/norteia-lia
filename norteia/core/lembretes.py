"""Cálculo de lembretes. Sem relógio escondido: quem chama passa o "agora"."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from .models import Tarefa

# Tarefa só com data (sem hora) lembra neste horário do dia
HORA_PADRAO = time(9, 0)

# (texto exibido, minutos antes do prazo). None = sem lembrete.
ANTECEDENCIAS: list[tuple[str, int | None]] = [
    ("Sem lembrete", None),
    ("Na hora", 0),
    ("5 minutos antes", 5),
    ("30 minutos antes", 30),
    ("1 hora antes", 60),
    ("1 dia antes", 1440),
]


def descrever(minutos: int) -> str:
    for texto, valor in ANTECEDENCIAS:
        if valor == minutos:
            return texto
    if minutos % 1440 == 0:
        return f"{minutos // 1440} dias antes"
    if minutos % 60 == 0:
        return f"{minutos // 60} horas antes"
    return f"{minutos} minutos antes"


@dataclass(frozen=True)
class Lembrete:
    tarefa: Tarefa
    instante: datetime      # hora local em que deveria tocar
    minutos_antes: int

    @property
    def titulo(self) -> str:
        return self.tarefa.titulo

    @property
    def adiado(self) -> bool:
        """Lembrete que voltou depois da soneca (minutos_antes = -1)."""
        return self.minutos_antes < 0

    @property
    def texto(self) -> str:
        if self.adiado:
            return "Lembrete adiado"
        if self.minutos_antes == 0:
            quando = "agora" if self.tarefa.prazo_hora else "hoje"
            return f"Vence {quando}"
        return f"Vence em {descrever(self.minutos_antes).replace(' antes', '')}"


def prazo_completo(t: Tarefa) -> datetime | None:
    if t.prazo is None:
        return None
    return datetime.combine(t.prazo, t.prazo_hora or HORA_PADRAO)


def instante_do_lembrete(t: Tarefa, minutos_antes: int) -> datetime | None:
    base = prazo_completo(t)
    return base - timedelta(minutes=minutos_antes) if base else None
