"""Matriz de Eisenhower: urgente x importante, calculada a partir de prioridade e prazo."""
from __future__ import annotations

from datetime import date, timedelta

from .models import Prioridade, Tarefa

Q1, Q2, Q3, Q4 = "q1", "q2", "q3", "q4"
NOMES = {
    Q1: ("Urgente e Importante", "Fazer agora"),
    Q2: ("Não Urgente e Importante", "Agendar"),
    Q3: ("Urgente e não importante", "Delegar ou resolver rápido"),
    Q4: ("Não urgente e não importante", "Eliminar ou deixar para depois"),
}
URGENTE_DIAS = 2          # prazo hoje, atrasado ou nos próximos 2 dias = urgente
IMPORTANTE_MIN = Prioridade.MEDIA


def quadrante(t: Tarefa, hoje: date, urgente_dias: int = URGENTE_DIAS) -> str:
    importante = int(t.prioridade) >= int(IMPORTANTE_MIN)
    urgente = t.prazo is not None and t.prazo <= hoje + timedelta(days=urgente_dias)
    if importante:
        return Q1 if urgente else Q2
    return Q3 if urgente else Q4


class Matriz:
    def __init__(self, servico):
        self.servico = servico

    def quadrantes(self, hoje: date | None = None, urgente_dias: int = URGENTE_DIAS) -> dict[str, list[Tarefa]]:
        from .servico import TODAS
        hoje = hoje or date.today()
        saida: dict[str, list[Tarefa]] = {Q1: [], Q2: [], Q3: [], Q4: []}
        for t in self.servico.listar(TODAS, hoje):
            if t.eh_nota:
                continue
            saida[quadrante(t, hoje, urgente_dias)].append(t)
        return saida

    def mover(self, tarefa_id: int, destino: str, hoje: date | None = None,
              urgente_dias: int = URGENTE_DIAS) -> Tarefa:
        """Muda prioridade e prazo para a tarefa cair no quadrante de destino."""
        hoje = hoje or date.today()
        t = self.servico.banco.obter_tarefa(tarefa_id)
        if t is None:
            raise ValueError("tarefa não encontrada")
        importante, urgente = destino in (Q1, Q2), destino in (Q1, Q3)
        if importante and int(t.prioridade) < int(IMPORTANTE_MIN):
            t.prioridade = Prioridade.ALTA
        elif not importante and int(t.prioridade) >= int(IMPORTANTE_MIN):
            t.prioridade = Prioridade.BAIXA
        limite = hoje + timedelta(days=urgente_dias)
        if urgente and (t.prazo is None or t.prazo > limite):
            t.prazo = hoje
        elif not urgente and t.prazo is not None and t.prazo <= limite:
            t.prazo = limite + timedelta(days=5)
        if t.inicio and t.prazo and t.inicio > t.prazo:
            t.inicio = None
        return self.servico.salvar(t)
