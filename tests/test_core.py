from datetime import date, timedelta

import pytest

from norteia.core import (CONCLUIDAS, HOJE, LIXEIRA, PROXIMOS, TODAS, Banco,
                          Prioridade, Servico, interpretar)

SEGUNDA = date(2026, 10, 19)  # dia fixo para os testes de data


@pytest.fixture
def svc():
    return Servico(Banco(":memory:"))


def test_interpretar_hoje_prioridade_tag():
    e = interpretar("Pagar conta hoje !3 #casa", SEGUNDA)
    assert e.titulo == "Pagar conta"
    assert e.prazo == SEGUNDA
    assert e.prioridade == Prioridade.ALTA
    assert e.tags == ["casa"]


def test_interpretar_amanha_e_dia_da_semana():
    assert interpretar("Estudar amanhã", SEGUNDA).prazo == SEGUNDA + timedelta(days=1)
    # segunda -> próxima sexta
    assert interpretar("Entregar relatório sexta", SEGUNDA).prazo == date(2026, 10, 23)
    # mesmo dia da semana vai para a semana seguinte
    assert interpretar("Reunião segunda", SEGUNDA).prazo == date(2026, 10, 26)


def test_interpretar_sem_atalhos_mantem_titulo():
    e = interpretar("Comprar pão")
    assert e.titulo == "Comprar pão" and e.prazo is None and e.tags == []


def test_criar_e_recuperar_tarefa_com_tags(svc):
    t = svc.adicionar_rapido("Ler artigo #estudo #ia !2")
    de_volta = svc.banco.obter_tarefa(t.id)
    assert de_volta.titulo == "Ler artigo"
    assert de_volta.tags == ["estudo", "ia"]
    assert de_volta.prioridade == Prioridade.MEDIA


def test_concluir_e_reabrir(svc):
    t = svc.adicionar_rapido("Tarefa")
    assert svc.alternar_conclusao(t.id).concluida
    assert [x.id for x in svc.listar(CONCLUIDAS)] == [t.id]
    assert svc.listar(TODAS) == []
    assert not svc.alternar_conclusao(t.id).concluida
    assert [x.id for x in svc.listar(TODAS)] == [t.id]


def test_lixeira_e_restaurar(svc):
    t = svc.adicionar_rapido("Apagar isto")
    svc.apagar(t.id)
    assert svc.listar(TODAS) == []
    assert [x.id for x in svc.listar(LIXEIRA)] == [t.id]
    svc.restaurar(t.id)
    assert [x.id for x in svc.listar(TODAS)] == [t.id]


def test_listas_hoje_e_proximos(svc):
    a = svc.adicionar_rapido("Atrasada ontem")
    a.prazo = SEGUNDA - timedelta(days=1)
    svc.salvar(a)
    b = svc.adicionar_rapido("Hoje")
    b.prazo = SEGUNDA
    svc.salvar(b)
    c = svc.adicionar_rapido("Daqui a 5 dias")
    c.prazo = SEGUNDA + timedelta(days=5)
    svc.salvar(c)
    d = svc.adicionar_rapido("Daqui a 30 dias")
    d.prazo = SEGUNDA + timedelta(days=30)
    svc.salvar(d)
    svc.adicionar_rapido("Sem data")

    assert {x.titulo for x in svc.listar(HOJE, SEGUNDA)} == {"Atrasada ontem", "Hoje"}
    assert {x.titulo for x in svc.listar(PROXIMOS, SEGUNDA)} == {
        "Atrasada ontem", "Hoje", "Daqui a 5 dias"}
    assert len(svc.listar(TODAS, SEGUNDA)) == 5


def test_projetos_filtram_tarefas(svc):
    p = svc.criar_projeto("Faculdade")
    svc.adicionar_rapido("Trabalho de SI", projeto_id=p.id)
    svc.adicionar_rapido("Outra coisa")
    assert [x.titulo for x in svc.listar(p.id)] == ["Trabalho de SI"]
    assert svc.contagens()[p.id] == 1


def test_ordenacao_por_prazo_e_prioridade(svc):
    svc.adicionar_rapido("X sem prazo")
    svc.adicionar_rapido("Y amanhã !1")
    svc.adicionar_rapido("Z amanhã !3")
    # com prazo vem antes de sem prazo; no mesmo dia, maior prioridade primeiro
    assert [t.titulo for t in svc.listar(TODAS)] == ["Z", "Y", "X sem prazo"]


def test_atrasada(svc):
    t = svc.adicionar_rapido("x")
    t.prazo = date.today() - timedelta(days=1)
    assert t.atrasada
    t.concluida_em = __import__("datetime").datetime.now()
    assert not t.atrasada
