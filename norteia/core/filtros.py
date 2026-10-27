"""Regras dos filtros salvos. Todos os critérios são opcionais e se combinam com E."""
from __future__ import annotations

from datetime import date, timedelta

from .models import Tarefa

# (texto exibido, valor) para o critério de prazo
PRAZOS = [
    ("Qualquer data", None),
    ("Atrasadas", "atrasadas"),
    ("Hoje (e atrasadas)", "hoje"),
    ("Próximos 7 dias", "7dias"),
    ("Com data", "com"),
    ("Sem data", "sem"),
]
NOMES_PRAZO = {valor: nome for nome, valor in PRAZOS}


def corresponde(t: Tarefa, c: dict, hoje: date | None = None) -> bool:
    hoje = hoje or date.today()
    if c.get("projeto_id") is not None and t.projeto_id != c["projeto_id"]:
        return False
    if c.get("tag") and c["tag"] not in t.tags:
        return False
    if int(t.prioridade) < int(c.get("prioridade_min", 0) or 0):
        return False
    texto = (c.get("texto") or "").strip().lower()
    if texto and texto not in t.titulo.lower() and texto not in t.notas.lower():
        return False
    prazo = c.get("prazo")
    if prazo == "sem":
        return t.prazo is None
    if prazo and t.prazo is None:
        return False
    if prazo == "atrasadas":
        return t.prazo < hoje
    if prazo == "hoje":
        return t.prazo <= hoje
    if prazo == "7dias":
        return t.prazo <= hoje + timedelta(days=7)
    return True


def descrever(c: dict, nome_projeto: str | None = None) -> str:
    partes = []
    if nome_projeto:
        partes.append(f"lista {nome_projeto}")
    if c.get("tag"):
        partes.append(f"#{c['tag']}")
    if c.get("prioridade_min"):
        partes.append(f"prioridade ≥ {c['prioridade_min']}")
    if c.get("prazo"):
        partes.append(NOMES_PRAZO.get(c["prazo"], c["prazo"]).lower())
    if c.get("texto"):
        partes.append(f"contém “{c['texto']}”")
    return ", ".join(partes) or "todas as tarefas"
