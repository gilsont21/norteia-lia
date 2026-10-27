from datetime import date, timedelta

import pytest

from norteia.core import Banco, Servico, chave_filtro, filtros

HOJE = date(2026, 10, 19)


@pytest.fixture
def svc():
    return Servico(Banco(":memory:"))


# ---------- subtarefas ----------
def test_subtarefa_herda_lista_e_nao_aparece_nas_listas(svc):
    p = svc.criar_projeto("Casa")
    pai = svc.adicionar_rapido("Mudança", projeto_id=p.id)
    sub = svc.adicionar_subtarefa(pai.id, "Embalar louça")
    assert sub.pai_id == pai.id and sub.projeto_id == p.id
    assert [t.titulo for t in svc.listar("todas")] == ["Mudança"]
    assert svc.contagens()["todas"] == 1


def test_progresso_das_subtarefas(svc):
    pai = svc.adicionar_rapido("Viagem")
    a = svc.adicionar_subtarefa(pai.id, "Passagem")
    svc.adicionar_subtarefa(pai.id, "Hotel")
    assert svc.progresso(pai.id) == (0, 2)
    svc.alternar_conclusao(a.id)
    assert svc.progresso(pai.id) == (1, 2)
    assert svc.listar("concluidas") == []  # subtarefa feita não vira linha em Concluídas


def test_subtarefa_exige_titulo(svc):
    pai = svc.adicionar_rapido("A")
    svc.adicionar_subtarefa(pai.id, "B")
    with pytest.raises(ValueError):
        svc.adicionar_subtarefa(pai.id, "   ")


def test_apagar_pai_leva_subtarefas_e_restaurar_traz_de_volta(svc):
    pai = svc.adicionar_rapido("A")
    s1 = svc.adicionar_subtarefa(pai.id, "B")
    s2 = svc.adicionar_subtarefa(pai.id, "C")
    svc.apagar(s2.id)  # apagada antes, de forma independente
    svc.apagar(pai.id)
    assert svc.subtarefas(pai.id) == []
    svc.restaurar(pai.id)
    assert [s.titulo for s in svc.subtarefas(pai.id)] == ["B"]  # C continua na lixeira
    assert s1.id in [s.id for s in svc.subtarefas(pai.id)]


# ---------- ordem manual ----------
def test_novas_tarefas_vao_para_o_fim_da_ordem(svc):
    a = svc.adicionar_rapido("A")
    b = svc.adicionar_rapido("B")
    c = svc.adicionar_rapido("C")
    assert a.ordem < b.ordem < c.ordem


def test_reordenar_grava_a_posicao(svc):
    a, b, c = (svc.adicionar_rapido(x) for x in "ABC")
    svc.reordenar([c.id, a.id, b.id])
    ordem = svc.banco.consultar("pai_id IS NULL", ordem="ordem, id")
    assert [t.titulo for t in ordem] == ["C", "A", "B"]


# ---------- filtros ----------
def _t(svc, texto, dias=None, **campos):
    t = svc.adicionar_rapido(texto)
    t.prazo = HOJE + timedelta(days=dias) if dias is not None else None
    for k, v in campos.items():
        setattr(t, k, v)
    return svc.salvar(t)


def test_filtro_por_prazo_e_prioridade(svc):
    _t(svc, "atrasada", -2, prioridade=3)
    _t(svc, "urgente-agora", 0, prioridade=3)
    _t(svc, "tranquila-agora", 0, prioridade=1)
    _t(svc, "semana", 5, prioridade=3)
    _t(svc, "longe", 30, prioridade=3)
    _t(svc, "sem data", None, prioridade=3)
    f = svc.criar_filtro("Urgente", {"prazo": "7dias", "prioridade_min": 2})
    nomes = sorted(t.titulo for t in svc.listar(chave_filtro(f.id), HOJE))
    assert nomes == ["atrasada", "semana", "urgente-agora"]
    assert svc.contagens(HOJE)[chave_filtro(f.id)] == 3


def test_filtro_por_lista_etiqueta_e_texto(svc):
    p = svc.criar_projeto("Faculdade")
    a = svc.adicionar_rapido("Estudar prova #si601", projeto_id=p.id)
    svc.adicionar_rapido("Estudar outra coisa #si601")
    svc.adicionar_rapido("Lavar louça", projeto_id=p.id)
    f = svc.criar_filtro("x", {"projeto_id": p.id, "tag": "si601", "texto": "estudar"})
    assert [t.id for t in svc.listar(chave_filtro(f.id))] == [a.id]


def test_filtro_sem_data_e_vazio(svc):
    _t(svc, "com", 1)
    _t(svc, "sem")
    sem = svc.criar_filtro("Sem data", {"prazo": "sem"})
    assert [t.titulo for t in svc.listar(chave_filtro(sem.id))] == ["sem"]
    tudo = svc.criar_filtro("Tudo", {})
    assert len(svc.listar(chave_filtro(tudo.id))) == 2


def test_apagar_filtro_e_filtro_inexistente(svc):
    f = svc.criar_filtro("A", {})
    svc.apagar_filtro(f.id)
    assert svc.banco.listar_filtros() == []
    assert svc.listar(chave_filtro(f.id)) == []


def test_filtro_nao_mostra_concluidas_nem_apagadas(svc):
    a = _t(svc, "a", 0)
    b = _t(svc, "b", 0)
    svc.alternar_conclusao(a.id)
    svc.apagar(b.id)
    f = svc.criar_filtro("x", {"prazo": "hoje"})
    assert svc.listar(chave_filtro(f.id), HOJE) == []


def test_descrever_filtro():
    assert filtros.descrever({}) == "todas as tarefas"
    assert "prioridade ≥ 2" in filtros.descrever({"prioridade_min": 2, "prazo": "hoje"})


def test_banco_antigo_ganha_tabela_de_filtros(tmp_path):
    import sqlite3
    arq = tmp_path / "v2.db"
    Banco(arq).fechar()
    con = sqlite3.connect(arq)
    con.execute("DROP TABLE filtro")
    con.execute("PRAGMA user_version = 2")
    con.commit()
    con.close()
    assert Banco(arq).listar_filtros() == []
