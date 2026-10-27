"""Modelos (templates): uma tarefa com subtarefas guardada para criar de novo com um clique."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .models import Prioridade, Registro, Tarefa, agora_utc


@dataclass
class Modelo:
    nome: str
    dados: dict
    uuid: str = ""


class Modelos:
    def __init__(self, servico):
        self.servico = servico
        self.banco = servico.banco

    def _foto(self, t: Tarefa, hoje: date) -> dict:
        return {
            "titulo": t.titulo, "notas": t.notas, "prioridade": int(t.prioridade), "tags": list(t.tags),
            "lembretes": list(t.lembretes), "repeticao": t.repeticao, "duracao_min": t.duracao_min,
            "tipo": t.tipo, "secao": t.secao, "insistir_min": t.insistir_min,
            "dias_ate_prazo": (t.prazo - hoje).days if t.prazo else None,
            "span": (t.prazo - t.inicio).days if t.prazo and t.inicio else 0,
            "prazo_hora": t.prazo_hora.isoformat() if t.prazo_hora else None,
            "subtarefas": [self._foto(s, hoje) for s in self.servico.subtarefas(t.id)],
        }

    def salvar_de_tarefa(self, tarefa_id: int, nome: str | None = None, hoje: date | None = None) -> Modelo:
        t = self.banco.obter_tarefa(tarefa_id)
        if t is None:
            raise ValueError("tarefa não encontrada")
        nome = (nome or t.titulo).strip()
        dados = self._foto(t, hoje or date.today())
        r = self.banco.salvar_registro(Registro("modelo", {"nome": nome, "tarefa": dados}))
        return Modelo(nome, dados, r.uuid)

    def listar(self) -> list[Modelo]:
        return sorted((Modelo(r.dados["nome"], r.dados["tarefa"], r.uuid)
                       for r in self.banco.listar_registros("modelo")), key=lambda m: m.nome.lower())

    def renomear(self, uuid: str, nome: str) -> None:
        r = self.banco.obter_registro_por_uuid(uuid)
        if r and nome.strip():
            r.dados["nome"] = nome.strip()
            self.banco.salvar_registro(r)

    def apagar(self, uuid: str) -> None:
        r = self.banco.obter_registro_por_uuid(uuid)
        if r:
            r.apagado_em = agora_utc()
            self.banco.salvar_registro(r)

    def _criar(self, d: dict, hoje: date, projeto_id: int | None, pai_id: int | None) -> Tarefa:
        prazo = None
        if d.get("dias_ate_prazo") is not None:
            prazo = hoje + timedelta(days=max(0, d["dias_ate_prazo"]))
        span = int(d.get("span", 0))
        t = self.banco.salvar_tarefa(Tarefa(
            titulo=d["titulo"], notas=d.get("notas", ""), projeto_id=projeto_id, pai_id=pai_id,
            prioridade=Prioridade(d.get("prioridade", 0)), prazo=prazo,
            inicio=(prazo - timedelta(days=span)) if prazo and span else None,
            prazo_hora=time.fromisoformat(d["prazo_hora"]) if d.get("prazo_hora") and prazo else None,
            repeticao=d.get("repeticao"), lembretes=list(d.get("lembretes", [])) if prazo else [],
            tags=list(d.get("tags", [])), duracao_min=d.get("duracao_min", 0), tipo=d.get("tipo", "tarefa"),
            secao=d.get("secao", ""), insistir_min=d.get("insistir_min", 0) if prazo else 0,
            ordem=self.banco.proxima_ordem()))
        for sub in d.get("subtarefas", []):
            self._criar(sub, hoje, projeto_id, t.id)
        return t

    def criar_tarefa(self, uuid: str, projeto_id: int | None = None, hoje: date | None = None) -> Tarefa:
        """Cria a tarefa (e subtarefas) do modelo. O prazo é recalculado a partir de hoje."""
        r = self.banco.obter_registro_por_uuid(uuid)
        if r is None or r.tipo != "modelo" or r.apagado_em is not None:
            raise ValueError("modelo não encontrado")
        return self._criar(r.dados["tarefa"], hoje or date.today(), projeto_id, None)
