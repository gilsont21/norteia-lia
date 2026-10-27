"""Quadro Kanban: como as tarefas se dividem em colunas e o que acontece ao arrastar uma para outra."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import Prioridade, Tarefa

MODOS = [("secao", "Seções"), ("data", "Data"), ("prioridade", "Prioridade"), ("projeto", "Lista")]
COLUNAS_DATA = [("atrasadas", "Atrasadas"), ("hoje", "Hoje"), ("amanha", "Amanhã"),
                ("semana", "Próximos 7 dias"), ("depois", "Mais tarde"), ("sem", "Sem data")]


@dataclass
class Coluna:
    chave: object
    titulo: str
    tarefas: list[Tarefa] = field(default_factory=list)
    aceita_soltar: bool = True


def modo_valido(modo: str, lista_atual) -> str:
    """Seções só fazem sentido dentro de uma lista (ou da Caixa de entrada)."""
    from .servico import CAIXA
    if modo == "secao" and not (isinstance(lista_atual, int) or lista_atual == CAIXA):
        return "data"
    return modo


def projeto_da_lista(lista_atual) -> int | None:
    return lista_atual if isinstance(lista_atual, int) else None


def balde_de_data(t: Tarefa, hoje: date) -> str:
    if t.prazo is None:
        return "sem"
    if t.prazo < hoje:
        return "atrasadas"
    if t.prazo == hoje:
        return "hoje"
    if t.prazo == hoje + timedelta(days=1):
        return "amanha"
    if t.prazo <= hoje + timedelta(days=7):
        return "semana"
    return "depois"


def colunas(servico, modo: str, tarefas: list[Tarefa], projeto_id: int | None = None,
            hoje: date | None = None) -> list[Coluna]:
    hoje = hoje or date.today()
    if modo == "secao":
        nomes = servico.banco.secoes_da_lista(projeto_id)
        cols = [Coluna("", "Sem seção")] + [Coluna(n, n) for n in nomes]
        por = {c.chave: c for c in cols}
        for t in tarefas:
            por.get(t.secao, cols[0]).tarefas.append(t)
        return cols
    if modo == "data":
        cols = [Coluna(k, n, aceita_soltar=(k != "atrasadas")) for k, n in COLUNAS_DATA]
        por = {c.chave: c for c in cols}
        for t in tarefas:
            por[balde_de_data(t, hoje)].tarefas.append(t)
        return cols
    if modo == "prioridade":
        nomes = {3: "Alta", 2: "Média", 1: "Baixa", 0: "Nenhuma"}
        cols = [Coluna(v, nomes[v]) for v in (3, 2, 1, 0)]
        por = {c.chave: c for c in cols}
        for t in tarefas:
            por[int(t.prioridade)].tarefas.append(t)
        return cols
    if modo == "projeto":
        cols = [Coluna(None, "Caixa de Entrada")] + [Coluna(p.id, p.nome) for p in servico.banco.listar_projetos()]
        por = {c.chave: c for c in cols}
        for t in tarefas:
            por.get(t.projeto_id, cols[0]).tarefas.append(t)
        return cols
    raise ValueError(f"modo desconhecido: {modo!r}")


def mover(servico, tarefa_id: int, modo: str, chave, hoje: date | None = None) -> Tarefa:
    """Arrastar para uma coluna muda o campo que a coluna representa."""
    hoje = hoje or date.today()
    t = servico.banco.obter_tarefa(tarefa_id)
    if t is None:
        raise ValueError("tarefa não encontrada")
    if modo == "secao":
        t.secao = chave or ""
    elif modo == "prioridade":
        t.prioridade = Prioridade(int(chave))
    elif modo == "data":
        if chave == "atrasadas":
            raise ValueError("não dá para arrastar para Atrasadas")
        destino = {"hoje": hoje, "amanha": hoje + timedelta(days=1), "semana": hoje + timedelta(days=7),
                   "depois": hoje + timedelta(days=30), "sem": None}[chave]
        if t.inicio and t.prazo and destino:
            t.inicio = destino - (t.prazo - t.inicio)
        t.prazo = destino
        if destino is None:
            t.prazo_hora, t.lembretes, t.repeticao, t.insistir_min = None, [], None, 0
    elif modo == "projeto":
        t.projeto_id = chave
        servico.salvar(t)
        for sub in servico.descendentes(tarefa_id):
            sub.projeto_id = chave
            servico.salvar(sub)
        return servico.banco.obter_tarefa(tarefa_id)
    else:
        raise ValueError(f"modo desconhecido: {modo!r}")
    return servico.salvar(t)


# ---- seções (colunas do modo "secao") ----
def criar_secao(servico, projeto_id: int | None, nome: str) -> None:
    nome = nome.strip()
    if not nome:
        raise ValueError("a seção precisa de um nome")
    atuais = servico.banco.secoes_da_lista(projeto_id)
    if nome not in atuais:
        servico.banco.definir_secoes(projeto_id, atuais + [nome])


def renomear_secao(servico, projeto_id: int | None, antigo: str, novo: str) -> None:
    novo = novo.strip()
    if not novo:
        raise ValueError("a seção precisa de um nome")
    atuais = servico.banco.secoes_da_lista(projeto_id)
    servico.banco.definir_secoes(projeto_id, [novo if n == antigo else n for n in atuais])
    for t in _tarefas_da_secao(servico, projeto_id, antigo):
        t.secao = novo
        servico.salvar(t)


def apagar_secao(servico, projeto_id: int | None, nome: str) -> None:
    """As tarefas da seção não são apagadas: voltam para "Sem seção"."""
    atuais = servico.banco.secoes_da_lista(projeto_id)
    servico.banco.definir_secoes(projeto_id, [n for n in atuais if n != nome])
    for t in _tarefas_da_secao(servico, projeto_id, nome):
        t.secao = ""
        servico.salvar(t)


def mover_secao(servico, projeto_id: int | None, nome: str, passo: int) -> None:
    atuais = servico.banco.secoes_da_lista(projeto_id)
    if nome not in atuais:
        return
    i = atuais.index(nome)
    j = i + passo
    if 0 <= j < len(atuais):
        atuais[i], atuais[j] = atuais[j], atuais[i]
        servico.banco.definir_secoes(projeto_id, atuais)


def _tarefas_da_secao(servico, projeto_id: int | None, nome: str) -> list[Tarefa]:
    cond = "projeto_id IS NULL" if projeto_id is None else "projeto_id = ?"
    args = (nome,) if projeto_id is None else (nome, projeto_id)
    return servico.banco.consultar(f"secao = ? AND {cond}", args)
