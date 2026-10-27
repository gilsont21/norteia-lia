"""Entidades do núcleo. Python puro, sem dependência de interface.

Pensado para sincronizar entre aparelhos: toda entidade tem um uuid (identificador único
no mundo todo), carimbos de data em UTC e exclusão "marcada" em vez de apagar de verdade.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from enum import IntEnum
from uuid import uuid4


def novo_uuid() -> str:
    return str(uuid4())


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class Prioridade(IntEnum):
    NENHUMA = 0
    BAIXA = 1
    MEDIA = 2
    ALTA = 3


@dataclass
class Projeto:
    nome: str
    cor: str = "#c39a3f"
    ordem: int = 0
    arquivado: bool = False
    uuid: str = field(default_factory=novo_uuid)
    atualizada_em: datetime = field(default_factory=agora_utc)
    apagado_em: datetime | None = None
    id: int | None = None
    pasta: str = ""                         # agrupa listas na barra lateral ("" = sem pasta)
    emoji: str = ""                         # aparece no lugar do ícone da lista
    visao: str = "lista"                    # como a lista abre: "lista", "kanban" ou "linha_tempo"
    tipo: str = "tarefas"                   # "tarefas" ou "notas" (lista de notas cria itens sem caixinha)
    inteligente: str = "todas"              # "todas" mostra as tarefas nas listas inteligentes; "nenhuma" esconde


@dataclass
class Tag:
    nome: str
    cor: str = "#8a8f98"
    uuid: str = field(default_factory=novo_uuid)
    atualizada_em: datetime = field(default_factory=agora_utc)
    id: int | None = None


@dataclass
class Filtro:
    """Lista inteligente salva. `criterios` guarda as regras (ver core/filtros.py)."""
    nome: str
    criterios: dict = field(default_factory=dict)
    uuid: str = field(default_factory=novo_uuid)
    atualizada_em: datetime = field(default_factory=agora_utc)
    apagado_em: datetime | None = None
    id: int | None = None


@dataclass
class Tarefa:
    titulo: str
    notas: str = ""
    projeto_id: int | None = None
    pai_id: int | None = None
    prioridade: Prioridade = Prioridade.NENHUMA
    prazo: date | None = None
    prazo_hora: time | None = None          # hora local; sem hora = dia inteiro
    repeticao: str | None = None            # regra no formato RRULE, ex.: FREQ=WEEKLY;BYDAY=MO
    lembretes: list[int] = field(default_factory=list)  # minutos antes do prazo
    concluida_em: datetime | None = None
    criada_em: datetime = field(default_factory=agora_utc)
    atualizada_em: datetime = field(default_factory=agora_utc)
    apagada_em: datetime | None = None
    ordem: int = 0
    tags: list[str] = field(default_factory=list)
    uuid: str = field(default_factory=novo_uuid)
    id: int | None = None
    fixada: bool = False                    # aparece no topo da lista
    descartada_em: datetime | None = None   # "não será feito"
    insistir_min: int = 0                   # lembrete constante: repete a cada N min até concluir (0 = desligado)
    inicio: date | None = None              # início de tarefa de vários dias (o fim é o `prazo`)
    duracao_min: int = 0                    # duração no calendário; 0 = padrão (60 min) quando tem hora
    secao: str = ""                         # coluna do Kanban dentro da lista
    tipo: str = "tarefa"                    # "tarefa" ou "nota" (nota não tem caixinha de conclusão)

    @property
    def eh_nota(self) -> bool:
        return self.tipo == "nota"

    @property
    def concluida(self) -> bool:
        return self.concluida_em is not None

    @property
    def descartada(self) -> bool:
        return self.descartada_em is not None

    @property
    def finalizada(self) -> bool:
        return self.concluida or self.descartada

    @property
    def atrasada(self) -> bool:
        if self.prazo is None or self.finalizada or self.apagada_em is not None:
            return False
        agora = datetime.now()
        if self.prazo < agora.date():
            return True
        return (
            self.prazo == agora.date()
            and self.prazo_hora is not None
            and self.prazo_hora < agora.time()
        )


@dataclass
class Registro:
    """Linha genérica que sincroniza: hábitos, marcações de hábito, sessões de foco, comentários,
    modelos e contagens regressivas. O conteúdo fica em `dados` (JSON); `tipo` diz o que é."""
    tipo: str
    dados: dict = field(default_factory=dict)
    uuid: str = field(default_factory=novo_uuid)
    atualizada_em: datetime = field(default_factory=agora_utc)
    apagado_em: datetime | None = None
    id: int | None = None
