"""Números para a tela de estatísticas: tarefas concluídas, tempo de foco, sequência de dias."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from dateutil import tz


@dataclass
class Resumo:
    concluidas_hoje: int
    concluidas_semana: int
    concluidas_total: int
    pendentes: int
    atrasadas: int
    foco_hoje_s: int
    foco_semana_s: int
    foco_total_s: int
    sessoes_total: int
    sequencia_dias: int          # dias seguidos (terminando hoje ou ontem) com pelo menos uma tarefa concluída
    melhor_sequencia: int


def _local(dt: datetime) -> date:
    """Data local de um instante UTC guardado no banco."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz.tzlocal()).date()


class Estatisticas:
    def __init__(self, servico):
        self.servico = servico
        self.banco = servico.banco

    def _datas_de_conclusao(self) -> list[date]:
        linhas = self.banco.consultar("concluida_em IS NOT NULL AND apagada_em IS NULL")
        return [_local(t.concluida_em) for t in linhas]

    def concluidas_por_dia(self, ini: date, fim: date) -> dict[date, int]:
        dias = {ini + timedelta(days=i): 0 for i in range((fim - ini).days + 1)}
        for d in self._datas_de_conclusao():
            if d in dias:
                dias[d] += 1
        return dias

    def foco_por_dia(self, ini: date, fim: date) -> dict[date, int]:
        return self.servico.foco.segundos_por_dia(ini, fim)

    def por_lista(self) -> list[tuple[str, int]]:
        """Tarefas concluídas por lista, da maior para a menor."""
        nomes = {p.id: p.nome for p in self.banco.listar_projetos() + self.banco.listar_projetos_arquivados()}
        contagem: dict[str, int] = {}
        for t in self.banco.consultar("concluida_em IS NOT NULL AND apagada_em IS NULL AND pai_id IS NULL"):
            nome = nomes.get(t.projeto_id, "Caixa de Entrada")
            contagem[nome] = contagem.get(nome, 0) + 1
        return sorted(contagem.items(), key=lambda x: (-x[1], x[0]))

    def resumo(self, hoje: date | None = None) -> Resumo:
        from .servico import HOJE, TODAS
        hoje = hoje or date.today()
        semana_ini = hoje - timedelta(days=6)
        datas = self._datas_de_conclusao()
        conj = set(datas)
        atual = 0
        d = hoje if hoje in conj else hoje - timedelta(days=1)
        while d in conj:
            atual += 1
            d -= timedelta(days=1)
        melhor = corrente = 0
        anterior = None
        for d in sorted(conj):
            corrente = corrente + 1 if anterior and (d - anterior).days == 1 else 1
            melhor = max(melhor, corrente)
            anterior = d
        sessoes = self.servico.foco.sessoes()
        ativas = self.servico.listar(TODAS, hoje)
        return Resumo(
            concluidas_hoje=sum(1 for x in datas if x == hoje),
            concluidas_semana=sum(1 for x in datas if semana_ini <= x <= hoje),
            concluidas_total=len(datas),
            pendentes=len(ativas),
            atrasadas=sum(1 for t in ativas if t.prazo and t.prazo < hoje),
            foco_hoje_s=sum(s.duracao_s for s in sessoes if s.inicio.date() == hoje),
            foco_semana_s=sum(s.duracao_s for s in sessoes if semana_ini <= s.inicio.date() <= hoje),
            foco_total_s=sum(s.duracao_s for s in sessoes),
            sessoes_total=len(sessoes),
            sequencia_dias=atual, melhor_sequencia=melhor)
