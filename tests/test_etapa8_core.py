"""Etapa 8 e extras: hábitos, foco, contagem regressiva, comentários, modelos, anexos, estatísticas."""
from datetime import date, datetime, time, timedelta

import pytest

from norteia.core import Banco, Servico
from norteia.core.foco import ConfigFoco, Cronometro, Sessao, formatar_duracao
from norteia.core.habitos import TODOS_OS_DIAS

HOJE = date(2026, 10, 26)      # segunda-feira
AGORA = datetime(2026, 10, 26, 9, 0, 0)


@pytest.fixture
def svc():
    return Servico(Banco(":memory:"))


# ---------------------------------------------------------------- hábitos
def test_criar_listar_e_validar(svc):
    h = svc.habitos.criar("Beber água", meta=8, unidade="copos", lembrete="10:00", inicio=HOJE)
    assert [x.nome for x in svc.habitos.listar()] == ["Beber água"] and h.dias == TODOS_OS_DIAS
    with pytest.raises(ValueError):
        svc.habitos.criar("  ")
    svc.habitos.arquivar(h.uuid)
    assert svc.habitos.listar() == [] and len(svc.habitos.listar(arquivados=True)) == 1
    svc.habitos.arquivar(h.uuid, False)
    svc.habitos.apagar(h.uuid)
    assert svc.habitos.listar(arquivados=None) == [] and svc.habitos.obter(h.uuid) is None


def test_marcar_e_desmarcar(svc):
    h = svc.habitos.criar("Ler", inicio=HOJE)
    assert not svc.habitos.concluido(h, HOJE)
    svc.habitos.alternar(h, HOJE)
    assert svc.habitos.concluido(h, HOJE) and svc.habitos.quantidade(h, HOJE) == 1
    svc.habitos.alternar(h, HOJE)
    assert not svc.habitos.concluido(h, HOJE)
    assert len(svc.banco.listar_registros("marcacao")) == 1          # mesma linha, sem duplicar


def test_meta_numerica_incrementa_e_zera(svc):
    h = svc.habitos.criar("Água", meta=3, inicio=HOJE)
    assert [svc.habitos.incrementar(h, HOJE) for _ in range(4)] == [1, 2, 3, 0]
    svc.habitos.definir_quantidade(h, HOJE, 2)
    assert not svc.habitos.concluido(h, HOJE)
    svc.habitos.alternar(h, HOJE)
    assert svc.habitos.quantidade(h, HOJE) == 3


def test_sequencia(svc):
    h = svc.habitos.criar("Treino", inicio=HOJE - timedelta(days=9))
    for i in (9, 8, 7, 6):                                   # 4 dias seguidos...
        svc.habitos.definir_quantidade(h, HOJE - timedelta(days=i), 1)
    for i in (3, 2, 1):                                      # ...falha, depois 3 até ontem
        svc.habitos.definir_quantidade(h, HOJE - timedelta(days=i), 1)
    assert svc.habitos.sequencia(h, HOJE) == (3, 4)          # hoje ainda pendente: não quebra
    svc.habitos.definir_quantidade(h, HOJE, 1)
    assert svc.habitos.sequencia(h, HOJE) == (4, 4)
    svc.habitos.definir_quantidade(h, HOJE - timedelta(days=1), 0)
    assert svc.habitos.sequencia(h, HOJE) == (1, 4)


def test_dias_da_semana_pulam_nos_dias_livres(svc):
    h = svc.habitos.criar("Academia", dias=[0, 2, 4], inicio=date(2026, 10, 5))   # seg, qua, sex
    for d in (date(2026, 10, 5), date(2026, 10, 7), date(2026, 10, 9), date(2026, 10, 12)):
        svc.habitos.definir_quantidade(h, d, 1)
    assert svc.habitos.sequencia(h, date(2026, 10, 13)) == (4, 4)       # terça é livre: não quebra
    assert not h.agendado(date(2026, 10, 6)) and h.agendado(date(2026, 10, 7))
    assert svc.habitos.taxa(h, date(2026, 10, 5), date(2026, 10, 12)) == 1.0      # 4 de 4 previstos


def test_taxa_e_total(svc):
    h = svc.habitos.criar("Ler", inicio=HOJE - timedelta(days=3))
    svc.habitos.definir_quantidade(h, HOJE - timedelta(days=3), 1)
    svc.habitos.definir_quantidade(h, HOJE - timedelta(days=1), 1)
    assert svc.habitos.taxa(h, HOJE - timedelta(days=3), HOJE) == 0.5
    assert svc.habitos.total_feitos(h) == 2
    assert svc.habitos.taxa(h, HOJE + timedelta(days=5), HOJE + timedelta(days=9)) == 0.0   # só futuro, nada previsto


def test_mes_do_habito(svc):
    h = svc.habitos.criar("Ler", dias=[0, 1, 2, 3, 4], inicio=date(2026, 10, 1))        # dias úteis
    svc.habitos.definir_quantidade(h, date(2026, 10, 1), 1)
    svc.habitos.definir_quantidade(h, date(2026, 10, 2), 0)
    mes = dict(svc.habitos.mes(h, 2026, 10, hoje=HOJE))
    assert mes[date(2026, 10, 1)] == "feito" and mes[date(2026, 10, 2)] == "perdido"
    assert mes[date(2026, 10, 3)] == "livre"                         # sábado
    assert mes[HOJE] == "pendente" and mes[date(2026, 10, 28)] == "futuro"
    assert len(mes) == 31


def test_lembrete_do_habito_uma_vez_por_dia(svc):
    h = svc.habitos.criar("Remédio", lembrete="08:30", inicio=HOJE)
    assert svc.habitos.lembretes_vencidos(datetime(2026, 10, 26, 8, 0)) == []          # cedo demais
    assert [x.nome for x in svc.habitos.lembretes_vencidos(AGORA)] == ["Remédio"]
    svc.habitos.marcar_avisado(h, HOJE)
    assert svc.habitos.lembretes_vencidos(AGORA) == []
    assert len(svc.habitos.lembretes_vencidos(AGORA + timedelta(days=1))) == 1          # amanhã de novo
    svc.habitos.alternar(h, HOJE + timedelta(days=1))
    assert svc.habitos.lembretes_vencidos(AGORA + timedelta(days=1)) == []              # já feito: não avisa


def test_pendentes_hoje(svc):
    a = svc.habitos.criar("A", inicio=HOJE)
    svc.habitos.criar("B", inicio=HOJE)
    svc.habitos.criar("C", dias=[5, 6], inicio=HOJE)                  # só fim de semana
    svc.habitos.alternar(a, HOJE)
    assert [h.nome for h in svc.habitos.pendentes_hoje(HOJE)] == ["B"]


# ---------------------------------------------------------------- cronômetro de foco
def test_pomodoro_completo_gera_sessao_e_pausa():
    c = Cronometro(ConfigFoco(foco_min=25, pausa_curta_min=5))
    c.iniciar(AGORA, "t1")
    assert c.fase == "foco" and c.restante(AGORA) == 1500
    assert c.tick(AGORA + timedelta(minutes=10)) == []
    ev = c.tick(AGORA + timedelta(minutes=25))
    assert [e.tipo for e in ev] == ["foco_completo"]
    s = ev[0].sessao
    assert (s.duracao_s, s.completa, s.tarefa_uuid, s.inicio) == (1500, True, "t1", AGORA)
    assert c.fase == "pausa_curta" and c.ciclo == 1
    fim = AGORA + timedelta(minutes=30)
    assert [e.tipo for e in c.tick(fim)] == ["pausa_completa"] and c.fase == "parado"


def test_pausa_longa_a_cada_quatro_ciclos():
    c = Cronometro(ConfigFoco(foco_min=1, pausa_curta_min=1, pausa_longa_min=2, ciclos_ate_pausa_longa=2))
    t = AGORA
    c.iniciar(t)
    c.tick(t := t + timedelta(minutes=1))
    assert c.fase == "pausa_curta"
    c.tick(t := t + timedelta(minutes=1))
    assert c.fase == "parado"
    c.iniciar(t)
    c.tick(t + timedelta(minutes=1))
    assert c.fase == "pausa_longa" and c.ciclo == 0 and c.total_s == 120


def test_pausar_e_retomar_nao_conta_o_tempo_parado():
    c = Cronometro()
    c.iniciar(AGORA)
    c.pausar(AGORA + timedelta(minutes=10))
    assert c.decorrido(AGORA + timedelta(minutes=50)) == 600 and c.tick(AGORA + timedelta(hours=3)) == []
    c.retomar(AGORA + timedelta(minutes=60))
    assert c.decorrido(AGORA + timedelta(minutes=65)) == 900
    assert c.restante(AGORA + timedelta(minutes=65)) == 600
    assert [e.tipo for e in c.tick(AGORA + timedelta(minutes=75))] == ["foco_completo"]


def test_parar_guarda_tempo_so_se_passou_de_um_minuto():
    c = Cronometro()
    c.iniciar(AGORA)
    assert c.parar(AGORA + timedelta(seconds=30)) is None and c.fase == "parado"
    c.iniciar(AGORA)
    s = c.parar(AGORA + timedelta(minutes=12))
    assert s.duracao_s == 720 and not s.completa
    c.iniciar(AGORA)
    c.tick(AGORA + timedelta(minutes=25))
    assert c.parar(AGORA + timedelta(minutes=26)) is None                 # parar durante a pausa não gera sessão


def test_cronometro_conta_para_cima():
    c = Cronometro(modo="cronometro")
    c.iniciar(AGORA)
    assert c.total_s is None and c.restante(AGORA) is None
    assert c.tick(AGORA + timedelta(hours=5)) == []
    assert c.parar(AGORA + timedelta(hours=1)).duracao_s == 3600


def test_pular_pausa():
    c = Cronometro(ConfigFoco(foco_min=1))
    c.iniciar(AGORA)
    c.tick(AGORA + timedelta(minutes=1))
    c.pular_pausa()
    assert c.fase == "parado"


def test_registrar_e_somar_sessoes(svc):
    t = svc.adicionar_rapido("Estudar")
    svc.foco.registrar(Sessao(AGORA, 1500, tarefa_uuid=t.uuid))
    svc.foco.registrar(Sessao(AGORA + timedelta(hours=1), 600, "cronometro", False, t.uuid))
    svc.foco.registrar(Sessao(AGORA - timedelta(days=1), 900))
    assert svc.foco.segundos_da_tarefa(t.uuid) == 2100
    dias = svc.foco.segundos_por_dia(HOJE - timedelta(days=2), HOJE)
    assert dias == {HOJE - timedelta(days=2): 0, HOJE - timedelta(days=1): 900, HOJE: 2100}
    assert [s.duracao_s for s in svc.foco.sessoes(HOJE, HOJE)] == [1500, 600]
    svc.foco.apagar(svc.foco.sessoes(HOJE, HOJE)[0].uuid)
    assert svc.foco.segundos_da_tarefa(t.uuid) == 600


def test_formatar_duracao():
    assert [formatar_duracao(s) for s in (0, 90, 3600, 3700, 7260)] == ["0 min", "1 min", "1 h 00 min", "1 h 01 min", "2 h 01 min"]


# ---------------------------------------------------------------- contagem regressiva
def test_contagem_regressiva(svc):
    c = svc.contagens_regressivas.criar("Prova de SAD", date(2026, 11, 5))
    assert c.dias(HOJE) == 10 and c.texto(HOJE) == "Faltam 10 dias"
    assert svc.contagens_regressivas.criar("Hoje", HOJE).texto(HOJE) == "É hoje!"
    assert svc.contagens_regressivas.criar("Amanhã", HOJE + timedelta(days=1)).texto(HOJE) == "Falta 1 dia"
    assert svc.contagens_regressivas.criar("Passou", HOJE - timedelta(days=3)).texto(HOJE) == "Há 3 dias"
    assert [x.nome for x in svc.contagens_regressivas.listar(HOJE)] == ["Hoje", "Amanhã", "Prova de SAD", "Passou"]
    with pytest.raises(ValueError):
        svc.contagens_regressivas.criar(" ", HOJE)


def test_contagem_anual_e_29_de_fevereiro(svc):
    aniv = svc.contagens_regressivas.criar("Aniversário", date(2000, 11, 3), anual=True)
    assert aniv.proxima_data(HOJE) == date(2026, 11, 3) and aniv.dias(HOJE) == 8
    assert aniv.proxima_data(date(2026, 11, 4)) == date(2027, 11, 3)
    bissexto = svc.contagens_regressivas.criar("Bissexto", date(2024, 2, 29), anual=True)
    assert bissexto.proxima_data(HOJE) == date(2027, 3, 1)


def test_editar_e_apagar_contagem(svc):
    c = svc.contagens_regressivas.criar("A", HOJE)
    c.nome = "B"
    svc.contagens_regressivas.salvar(c)
    assert svc.contagens_regressivas.listar(HOJE)[0].nome == "B"
    svc.contagens_regressivas.apagar(c.uuid)
    assert svc.contagens_regressivas.listar(HOJE) == []


# ---------------------------------------------------------------- comentários
def test_comentarios(svc):
    t = svc.adicionar_rapido("Tarefa")
    a = svc.comentarios.adicionar(t.id, "primeiro")
    svc.comentarios.adicionar(t.id, "  segundo  ")
    assert [c.texto for c in svc.comentarios.listar(t.id)] == ["primeiro", "segundo"]
    svc.comentarios.editar(a.uuid, "primeiro (editado)")
    svc.comentarios.apagar(svc.comentarios.listar(t.id)[1].uuid)
    assert [c.texto for c in svc.comentarios.listar(t.id)] == ["primeiro (editado)"]
    assert svc.comentarios.quantidade(t.id) == 1
    with pytest.raises(ValueError):
        svc.comentarios.adicionar(t.id, "   ")
    with pytest.raises(ValueError):
        svc.comentarios.adicionar(9999, "x")


# ---------------------------------------------------------------- modelos
def test_modelo_com_subtarefas_e_prazo_relativo(svc):
    t = svc.adicionar_rapido("Viagem #lazer !2")
    t.prazo, t.lembretes, t.notas = HOJE + timedelta(days=10), [60], "levar documentos"
    svc.salvar(t)
    sub = svc.adicionar_subtarefa(t.id, "Passagem")
    svc.adicionar_subtarefa(sub.id, "Comparar preços")
    m = svc.modelos.salvar_de_tarefa(t.id, "Modelo de viagem", HOJE)
    assert [x.nome for x in svc.modelos.listar()] == ["Modelo de viagem"]
    nova = svc.modelos.criar_tarefa(m.uuid, hoje=date(2026, 12, 1))
    assert nova.id != t.id and nova.prazo == date(2026, 12, 11)                 # 10 dias depois de "hoje"
    assert nova.tags == ["lazer"] and nova.lembretes == [60] and nova.notas == "levar documentos"
    assert [(x.titulo, n) for x, n in svc.arvore(nova.id)] == [("Passagem", 1), ("Comparar preços", 2)]
    svc.modelos.renomear(m.uuid, "Viagem padrão")
    svc.modelos.apagar(m.uuid)
    assert svc.modelos.listar() == []
    with pytest.raises(ValueError):
        svc.modelos.criar_tarefa(m.uuid)


def test_modelo_de_tarefa_sem_prazo_nao_ganha_lembrete(svc):
    t = svc.adicionar_rapido("Sem data")
    m = svc.modelos.salvar_de_tarefa(t.id)
    assert svc.modelos.criar_tarefa(m.uuid, projeto_id=None).prazo is None


# ---------------------------------------------------------------- anexos
def test_anexos(tmp_path):
    svc = Servico(Banco(":memory:"), pasta_dados=tmp_path / "dados")
    t = svc.adicionar_rapido("Com anexo")
    origem = tmp_path / "relatório final?.pdf"
    origem.write_bytes(b"%PDF-1.4 teste")
    a = svc.anexos.adicionar(t.id, origem)
    assert a.nome == "relatório final_.pdf" and a.tamanho == 14
    assert open(a.caminho, "rb").read() == b"%PDF-1.4 teste"
    assert [x.nome for x in svc.anexos.listar(t.id)] == [a.nome]
    svc.anexos.remover(a.id)
    assert svc.anexos.listar(t.id) == [] and not __import__("os").path.exists(a.caminho)
    with pytest.raises(ValueError):
        svc.anexos.adicionar(t.id, tmp_path / "nao-existe.txt")


def test_anexos_exigem_pasta_de_dados(tmp_path):
    svc = Servico(Banco(":memory:"))
    with pytest.raises(RuntimeError):
        svc.anexos.adicionar(1, tmp_path)


# ---------------------------------------------------------------- estatísticas
def test_estatisticas_e_sequencia(svc):
    from norteia.core.models import agora_utc
    for i, (dias_atras, qtd) in enumerate([(0, 2), (1, 1), (2, 1), (5, 1)]):
        for _ in range(qtd):
            t = svc.adicionar_rapido(f"feita {i}")
            t.concluida_em = agora_utc() - timedelta(days=dias_atras)
            svc.banco.salvar_tarefa(t)
    svc.adicionar_rapido("pendente")
    atrasada = svc.adicionar_rapido("atrasada")
    atrasada.prazo = date.today() - timedelta(days=2)
    svc.salvar(atrasada)
    svc.foco.registrar(Sessao(datetime.now(), 1500))
    r = svc.estatisticas.resumo(date.today())
    assert r.concluidas_hoje == 2 and r.concluidas_semana == 5 and r.concluidas_total == 5
    assert r.pendentes == 2 and r.atrasadas == 1
    assert r.sequencia_dias == 3 and r.melhor_sequencia == 3
    assert r.foco_hoje_s == 1500 and r.sessoes_total == 1
    por_dia = svc.estatisticas.concluidas_por_dia(date.today() - timedelta(days=6), date.today())
    assert sum(por_dia.values()) == 5 and por_dia[date.today()] == 2
    assert svc.estatisticas.por_lista() == [("Caixa de Entrada", 5)]


def test_sequencia_comeca_ontem_se_hoje_nada_foi_feito(svc):
    from norteia.core.models import agora_utc
    t = svc.adicionar_rapido("ontem")
    t.concluida_em = agora_utc() - timedelta(days=1)
    svc.banco.salvar_tarefa(t)
    r = svc.estatisticas.resumo(date.today())
    assert r.sequencia_dias == 1 and r.concluidas_hoje == 0
