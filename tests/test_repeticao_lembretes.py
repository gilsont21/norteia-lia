from datetime import date, datetime, time, timedelta

import pytest

from norteia.core import Banco, Servico, interpretar
from norteia.core import recorrencia
from norteia.core.lembretes import descrever as descrever_antecedencia

SEG = date(2026, 10, 19)  # uma segunda-feira


@pytest.fixture
def svc():
    return Servico(Banco(":memory:"))


# ---------- entrada rápida ----------
def test_interpretar_hora_com_h_e_dois_pontos():
    assert interpretar("Reunião às 14h", SEG).prazo_hora == time(14, 0)
    assert interpretar("Dentista as 9:30 amanhã", SEG).prazo_hora == time(9, 30)
    assert interpretar("Ligar @18h45", SEG).prazo_hora == time(18, 45)


def test_hora_vira_prazo_de_hoje_e_lembrete_na_hora():
    e = interpretar("Remédio às 8h", SEG)
    assert e.titulo == "Remédio" and e.prazo == SEG and e.lembretes == [0]


def test_hora_invalida_nao_e_interpretada():
    e = interpretar("Comprar 99h de cabo", SEG)
    assert e.prazo_hora is None and "99h" in e.titulo


def test_interpretar_repeticoes():
    assert interpretar("Academia todo dia às 7h", SEG).repeticao == "FREQ=DAILY"
    assert interpretar("Relatório toda semana", SEG).repeticao == "FREQ=WEEKLY"
    assert interpretar("Aluguel todo mês", SEG).repeticao == "FREQ=MONTHLY"
    assert interpretar("Standup dias úteis às 9:30", SEG).repeticao == recorrencia.DIAS_UTEIS
    e = interpretar("Beber água todo dia", SEG)
    assert e.titulo == "Beber água" and e.prazo == SEG


# ---------- próxima ocorrência ----------
def test_proxima_diaria_semanal_mensal_anual():
    assert recorrencia.proxima("FREQ=DAILY", SEG, SEG) == date(2026, 10, 20)
    assert recorrencia.proxima("FREQ=WEEKLY", SEG, SEG) == date(2026, 10, 26)
    assert recorrencia.proxima("FREQ=MONTHLY", SEG, SEG) == date(2026, 11, 19)
    assert recorrencia.proxima("FREQ=YEARLY", SEG, SEG) == date(2027, 10, 19)


def test_proxima_dias_uteis_pula_fim_de_semana():
    sexta = date(2026, 10, 23)
    assert recorrencia.proxima(recorrencia.DIAS_UTEIS, sexta, sexta) == date(2026, 10, 26)


def test_proxima_com_intervalo_e_dias_da_semana():
    assert recorrencia.proxima("FREQ=WEEKLY;INTERVAL=2", SEG, SEG) == date(2026, 11, 2)
    # seg e qua: depois de segunda vem quarta
    assert recorrencia.proxima("FREQ=WEEKLY;BYDAY=MO,WE", SEG, SEG) == date(2026, 10, 21)


def test_concluir_com_atraso_cria_proxima_no_futuro():
    # tarefa diária vencida há 3 dias, concluída hoje: próxima é amanhã, não ontem
    ha_3_dias = SEG - timedelta(days=3)
    assert recorrencia.proxima("FREQ=DAILY", ha_3_dias, SEG) == date(2026, 10, 20)


def test_concluir_antecipado_respeita_o_prazo():
    daqui_2 = SEG + timedelta(days=2)
    assert recorrencia.proxima("FREQ=DAILY", daqui_2, SEG) == date(2026, 10, 22)


def test_regra_invalida():
    assert not recorrencia.valida("isto não é regra")
    assert recorrencia.valida("FREQ=DAILY")


def test_descrever_regras():
    assert recorrencia.descrever(None) == "Não repete"
    assert recorrencia.descrever("FREQ=DAILY") == "Todo dia"
    assert recorrencia.descrever("FREQ=WEEKLY;INTERVAL=2") == "A cada 2 semanas"
    assert recorrencia.descrever("FREQ=WEEKLY;BYDAY=MO,WE") == "A cada semana (seg, qua)"


# ---------- concluir tarefa que repete ----------
def test_concluir_repetida_gera_a_proxima_com_os_mesmos_dados(svc):
    t = svc.adicionar_rapido("Academia todo dia às 7h #saude !2")
    t.prazo = SEG
    svc.salvar(t)
    svc.alternar_conclusao(t.id, hoje=SEG)

    abertas = svc.listar("todas", SEG)
    assert len(abertas) == 1
    nova = abertas[0]
    assert nova.id != t.id and nova.uuid != t.uuid
    assert nova.prazo == date(2026, 10, 20) and nova.prazo_hora == time(7, 0)
    assert nova.repeticao == "FREQ=DAILY" and nova.tags == ["saude"] and nova.lembretes == [0]
    assert [x.id for x in svc.listar("concluidas")] == [t.id]


def test_concluir_tarefa_comum_nao_cria_outra(svc):
    t = svc.adicionar_rapido("Comprar pão hoje")
    svc.alternar_conclusao(t.id)
    assert svc.listar("todas") == []


def test_reabrir_repetida_nao_duplica(svc):
    t = svc.adicionar_rapido("Diária todo dia")
    svc.alternar_conclusao(t.id, hoje=SEG)
    svc.alternar_conclusao(t.id, hoje=SEG)  # reabre a primeira
    assert len(svc.listar("todas", SEG)) == 2  # a reaberta e a próxima, sem criar uma terceira


# ---------- lembretes ----------
def _tarefa(svc, prazo, hora, lembretes):
    t = svc.adicionar_rapido("Lembrar")
    t.prazo, t.prazo_hora, t.lembretes = prazo, hora, lembretes
    return svc.salvar(t)


def test_lembrete_na_hora_dispara_so_depois(svc):
    t = _tarefa(svc, SEG, time(14, 0), [0])
    assert svc.lembretes_vencidos(datetime(2026, 10, 19, 13, 59)) == []
    devidos = svc.lembretes_vencidos(datetime(2026, 10, 19, 14, 0, 30))
    assert [d.tarefa.id for d in devidos] == [t.id]
    assert devidos[0].texto == "Vence agora"


def test_lembrete_antecipado(svc):
    _tarefa(svc, SEG, time(14, 0), [30])
    assert svc.lembretes_vencidos(datetime(2026, 10, 19, 13, 29)) == []
    d = svc.lembretes_vencidos(datetime(2026, 10, 19, 13, 31))
    assert len(d) == 1 and d[0].texto == "Vence em 30 minutos"


def test_cada_lembrete_avisa_uma_vez_so(svc):
    _tarefa(svc, SEG, time(14, 0), [0])
    agora = datetime(2026, 10, 19, 14, 1)
    d = svc.lembretes_vencidos(agora)
    svc.marcar_avisado(d[0])
    assert svc.lembretes_vencidos(agora) == []


def test_varios_lembretes_na_mesma_tarefa(svc):
    _tarefa(svc, SEG, time(14, 0), [0, 60])
    d = svc.lembretes_vencidos(datetime(2026, 10, 19, 14, 5))
    assert sorted(x.minutos_antes for x in d) == [0, 60]


def test_dia_inteiro_lembra_as_9h(svc):
    _tarefa(svc, SEG, None, [0])
    assert svc.lembretes_vencidos(datetime(2026, 10, 19, 8, 59)) == []
    assert len(svc.lembretes_vencidos(datetime(2026, 10, 19, 9, 1))) == 1


def test_lembrete_muito_velho_e_ignorado(svc):
    _tarefa(svc, SEG - timedelta(days=2), time(14, 0), [0])
    assert svc.lembretes_vencidos(datetime(2026, 10, 19, 10, 0)) == []


def test_tarefa_concluida_ou_apagada_nao_lembra(svc):
    a = _tarefa(svc, SEG, time(14, 0), [0])
    b = _tarefa(svc, SEG, time(14, 0), [0])
    svc.alternar_conclusao(a.id)
    svc.apagar(b.id)
    assert svc.lembretes_vencidos(datetime(2026, 10, 19, 14, 5)) == []


def test_tarefa_sem_lembrete_nao_avisa(svc):
    _tarefa(svc, SEG, time(14, 0), [])
    assert svc.lembretes_vencidos(datetime(2026, 10, 19, 14, 5)) == []


def test_descrever_antecedencia():
    assert descrever_antecedencia(0) == "Na hora"
    assert descrever_antecedencia(1440) == "1 dia antes"
    assert descrever_antecedencia(180) == "3 horas antes"
    assert descrever_antecedencia(45) == "45 minutos antes"


def test_ordenacao_considera_hora(svc):
    _tarefa(svc, SEG, time(16, 0), [])
    _tarefa(svc, SEG, time(8, 0), [])
    _tarefa(svc, SEG, None, [])
    horas = [t.prazo_hora for t in svc.listar("hoje", SEG)]
    assert horas == [time(8, 0), time(16, 0), None]
