from datetime import date, datetime, time, timedelta

import pytest

from norteia.core import Banco, Servico, interpretar
from norteia.core.servico import MAX_NIVEIS, AMANHA

HOJE = date(2026, 10, 26)  # segunda-feira


@pytest.fixture
def svc():
    return Servico(Banco(":memory:"))


# ---------- entrada rápida ----------
@pytest.mark.parametrize("texto,esperado", [
    ("Pagar conta depois de amanhã", date(2026, 10, 28)),
    ("Revisar daqui a 3 dias", date(2026, 10, 29)),
    ("Reunião em 2 semanas", date(2026, 11, 9)),
    ("Renovar daqui a 1 mês", date(2026, 11, 26)),
    ("Planejar semana que vem", date(2026, 11, 2)),
    ("Fechar mês que vem", date(2026, 11, 26)),
    ("Aluguel dia 30", date(2026, 10, 30)),
    ("Aluguel dia 5", date(2026, 11, 5)),
    ("Prova 15/11", date(2026, 11, 15)),
    ("Prova 03/10", date(2027, 10, 3)),
    ("Formatura 20/12/2027", date(2027, 12, 20)),
])
def test_datas_por_extenso(texto, esperado):
    e = interpretar(texto, HOJE)
    assert e.prazo == esperado
    # o trecho da data sai do título
    assert e.titulo in ("Pagar conta", "Revisar", "Reunião", "Renovar", "Planejar", "Fechar",
                        "Aluguel", "Prova", "Formatura")


def test_dia_31_pula_mes_sem_dia_31():
    e = interpretar("Fechar caixa dia 31", date(2026, 11, 10))
    assert e.prazo == date(2026, 12, 31)


def test_data_invalida_fica_no_titulo():
    e = interpretar("Evento 31/02", HOJE)
    assert e.prazo is None and "31/02" in e.titulo


def test_til_escolhe_a_lista(svc):
    prov = svc.criar_projeto("Faculdade")
    t = svc.adicionar_rapido("Estudar ~Fac !2")
    assert t.projeto_id == prov.id and t.titulo == "Estudar" and int(t.prioridade) == 2


def test_til_desconhecido_nao_perde_texto(svc):
    t = svc.adicionar_rapido("Estudar ~Inexistente")
    assert t.projeto_id is None and "Inexistente" in t.titulo


def test_lista_amanha(svc):
    from datetime import date as d
    hoje = d.today()
    a = svc.adicionar_rapido("amanhã cedo")
    svc.adicionar_rapido("hoje mesmo-x")
    svc.adicionar_rapido("depois de amanhã sim")
    assert [t.titulo for t in svc.listar(AMANHA)] == ["cedo"] or a.prazo == hoje + timedelta(days=1)
    assert [t.id for t in svc.listar(AMANHA)] == [a.id]


# ---------- projetos ----------
def test_renomear_cor_e_ordem_do_projeto(svc):
    a = svc.criar_projeto("A")
    b = svc.criar_projeto("B")
    svc.renomear_projeto(a.id, "  Casa ")
    svc.definir_cor_projeto(a.id, "#112233")
    assert svc.banco.obter_projeto(a.id).nome == "Casa"
    assert svc.banco.obter_projeto(a.id).cor == "#112233"
    svc.reordenar_projetos([b.id, a.id])
    assert [p.nome for p in svc.banco.listar_projetos()] == ["B", "Casa"]
    with pytest.raises(ValueError):
        svc.renomear_projeto(a.id, "   ")


def test_arquivar_projeto_esconde_da_barra_e_das_listas_inteligentes(svc):
    p = svc.criar_projeto("Velho")
    t = svc.adicionar_rapido("tarefa antiga hoje", p.id)
    assert t.id in [x.id for x in svc.listar("hoje")]
    svc.arquivar_projeto(p.id)
    assert p.id not in [x.id for x in svc.banco.listar_projetos()]
    assert p.id in [x.id for x in svc.banco.listar_projetos_arquivados()]
    assert t.id not in [x.id for x in svc.listar("todas")]
    assert t.id in [x.id for x in svc.listar(p.id)]       # abrindo a lista arquivada ainda dá para ver
    svc.arquivar_projeto(p.id, False)
    assert t.id in [x.id for x in svc.listar("todas")]


def test_apagar_projeto_manda_tarefas_para_lixeira_e_restaurar_traz_de_volta(svc):
    p = svc.criar_projeto("Temporário")
    a = svc.adicionar_rapido("a", p.id)
    b = svc.adicionar_rapido("b", p.id)
    svc.apagar(b.id)                       # já estava na lixeira por conta própria
    svc.apagar_projeto(p.id)
    assert p.id not in [x.id for x in svc.banco.listar_projetos()]
    assert {t.id for t in svc.listar("lixeira")} == {a.id, b.id}
    svc.restaurar_projeto(p.id)
    assert p.id in [x.id for x in svc.banco.listar_projetos()]
    assert [t.id for t in svc.listar(p.id)] == [a.id]       # b continua na lixeira
    assert [t.id for t in svc.listar("lixeira")] == [b.id]


def test_restaurar_tarefa_de_lista_apagada_vai_para_caixa(svc):
    p = svc.criar_projeto("Sumiu")
    t = svc.adicionar_rapido("x", p.id)
    svc.apagar_projeto(p.id)
    svc.restaurar(t.id)
    assert svc.banco.obter_tarefa(t.id).projeto_id is None
    assert t.id in [x.id for x in svc.listar("caixa")]


# ---------- etiquetas ----------
def test_renomear_tag(svc):
    a = svc.adicionar_rapido("a #prova")
    svc.renomear_tag("prova", "Exame")
    assert svc.banco.obter_tarefa(a.id).tags == ["exame"]
    assert [g.nome for g in svc.banco.listar_tags()] == ["exame"]


def test_renomear_para_nome_existente_funde(svc):
    a = svc.adicionar_rapido("a #velha")
    b = svc.adicionar_rapido("b #nova #velha")
    svc.renomear_tag("velha", "nova")
    assert svc.banco.obter_tarefa(a.id).tags == ["nova"]
    assert svc.banco.obter_tarefa(b.id).tags == ["nova"]
    assert [g.nome for g in svc.banco.listar_tags()] == ["nova"]


def test_apagar_tag_tira_das_tarefas(svc):
    a = svc.adicionar_rapido("a #x #y")
    svc.apagar_tag("x")
    assert svc.banco.obter_tarefa(a.id).tags == ["y"]
    assert [g.nome for g in svc.banco.listar_tags()] == ["y"]


def test_cor_da_tag(svc):
    svc.adicionar_rapido("a #x")
    svc.definir_cor_tag("x", "#ff0000")
    assert svc.banco.obter_tag("x").cor == "#ff0000"
    with pytest.raises(ValueError):
        svc.definir_cor_tag("nao-existe", "#000000")


# ---------- duplicar, fixar, não será feito ----------
def test_duplicar_copia_subtarefas_sem_conclusao(svc):
    pai = svc.adicionar_rapido("Viagem !2 #ferias")
    sub = svc.adicionar_subtarefa(pai.id, "Passagem")
    svc.alternar_conclusao(sub.id)
    copia = svc.duplicar(pai.id)
    assert copia.id != pai.id and copia.uuid != pai.uuid
    assert copia.titulo == "Viagem" and copia.tags == ["ferias"] and int(copia.prioridade) == 2
    filhas = svc.subtarefas(copia.id)
    assert [s.titulo for s in filhas] == ["Passagem"] and not filhas[0].concluida
    assert svc.progresso(pai.id) == (1, 1)          # original intacto


def test_fixar_vai_para_o_topo(svc):
    a = svc.adicionar_rapido("a")
    b = svc.adicionar_rapido("b")
    svc.alternar_fixada(b.id)
    assert [t.id for t in svc.listar("todas")] == [b.id, a.id]
    svc.alternar_fixada(b.id)
    assert [t.id for t in svc.listar("todas")] == [a.id, b.id]


def test_nao_sera_feito_sai_das_ativas_e_vai_para_concluidas(svc):
    t = svc.adicionar_rapido("desistir hoje-x")
    svc.alternar_descarte(t.id)
    assert t.id not in [x.id for x in svc.listar("todas")]
    assert t.id in [x.id for x in svc.listar("concluidas")]
    assert svc.banco.obter_tarefa(t.id).descartada
    assert not svc.banco.obter_tarefa(t.id).atrasada
    svc.alternar_conclusao(t.id)                     # clicar na caixinha reabre
    assert t.id in [x.id for x in svc.listar("todas")]


def test_descartar_tarefa_repetida_cria_a_proxima(svc):
    t = svc.adicionar_rapido("regar todo dia")
    svc.alternar_descarte(t.id)
    ativas = svc.listar("todas")
    assert len(ativas) == 1 and ativas[0].id != t.id and ativas[0].prazo > date.today()


# ---------- subtarefas em vários níveis ----------
def test_subtarefas_em_varios_niveis_e_limite(svc):
    raiz = svc.adicionar_rapido("raiz")
    atual = raiz
    for n in range(1, MAX_NIVEIS):
        atual = svc.adicionar_subtarefa(atual.id, f"nivel {n}")
    assert svc.nivel(atual.id) == MAX_NIVEIS - 1
    with pytest.raises(ValueError):
        svc.adicionar_subtarefa(atual.id, "fundo demais")
    assert [(t.titulo, n) for t, n in svc.arvore(raiz.id)] == [(f"nivel {i}", i) for i in range(1, MAX_NIVEIS)]


def test_apagar_e_restaurar_cascata_em_todos_os_niveis(svc):
    a = svc.adicionar_rapido("a")
    b = svc.adicionar_subtarefa(a.id, "b")
    c = svc.adicionar_subtarefa(b.id, "c")
    svc.apagar(a.id)
    assert all(svc.banco.obter_tarefa(i).apagada_em for i in (a.id, b.id, c.id))
    svc.restaurar(a.id)
    assert not any(svc.banco.obter_tarefa(i).apagada_em for i in (a.id, b.id, c.id))


def test_duplicar_copia_todos_os_niveis(svc):
    a = svc.adicionar_rapido("a")
    b = svc.adicionar_subtarefa(a.id, "b")
    svc.adicionar_subtarefa(b.id, "c")
    copia = svc.duplicar(a.id)
    assert [(t.titulo, n) for t, n in svc.arvore(copia.id)] == [("b", 1), ("c", 2)]


# ---------- lembretes: soneca, constante, resumo ----------
def _tarefa_com_lembrete(svc, hora=time(10, 0), insistir=0, dia=None):
    t = svc.adicionar_rapido("reunião")
    t.prazo = dia or date(2026, 10, 26)
    t.prazo_hora = hora
    t.lembretes = [0]
    t.insistir_min = insistir
    return svc.salvar(t)


def test_lembrete_unico_toca_uma_vez(svc):
    t = _tarefa_com_lembrete(svc)
    [l] = svc.lembretes_vencidos(datetime(2026, 10, 26, 10, 1))
    svc.marcar_avisado(l)
    assert svc.lembretes_vencidos(datetime(2026, 10, 26, 10, 30)) == []


def test_soneca_volta_depois_do_tempo(svc):
    t = _tarefa_com_lembrete(svc)
    [l] = svc.lembretes_vencidos(datetime(2026, 10, 26, 10, 0))
    svc.marcar_avisado(l)
    svc.adiar(t.id, 10, datetime(2026, 10, 26, 10, 0))
    assert svc.lembretes_vencidos(datetime(2026, 10, 26, 10, 5)) == []
    [volta] = svc.lembretes_vencidos(datetime(2026, 10, 26, 10, 10))
    assert volta.adiado and volta.texto == "Lembrete adiado" and volta.tarefa.id == t.id
    svc.marcar_avisado(volta)
    assert svc.lembretes_vencidos(datetime(2026, 10, 26, 10, 20)) == []


def test_soneca_para_amanha_as_9h(svc):
    t = _tarefa_com_lembrete(svc)
    ate = svc.adiar_para_amanha(t.id, datetime(2026, 10, 26, 22, 0))
    assert ate == datetime(2026, 10, 27, 9, 0)


def test_soneca_some_se_a_tarefa_for_concluida(svc):
    t = _tarefa_com_lembrete(svc)
    svc.adiar(t.id, 5, datetime(2026, 10, 26, 10, 0))
    svc.alternar_conclusao(t.id)
    assert svc.lembretes_vencidos(datetime(2026, 10, 26, 11, 0)) == []
    assert svc.banco.sonecas() == []


def test_lembrete_constante_repete_ate_concluir(svc):
    t = _tarefa_com_lembrete(svc, insistir=10)
    toques = []
    for minuto in (0, 3, 10, 12, 20, 25):
        agora = datetime(2026, 10, 26, 10, minuto)
        for l in svc.lembretes_vencidos(agora):
            svc.marcar_avisado(l)
            toques.append(minuto)
    assert toques == [0, 10, 20]
    svc.alternar_conclusao(t.id)
    assert svc.lembretes_vencidos(datetime(2026, 10, 26, 10, 30)) == []


def test_lembrete_constante_perdido_toca_so_o_mais_recente(svc):
    _tarefa_com_lembrete(svc, insistir=10)
    # o app ficou fechado: não despeja vários avisos de uma vez
    avisos = svc.lembretes_vencidos(datetime(2026, 10, 26, 10, 45))
    assert len(avisos) == 1 and avisos[0].instante == datetime(2026, 10, 26, 10, 40)
    svc.marcar_avisado(avisos[0])
    assert svc.lembretes_vencidos(datetime(2026, 10, 26, 10, 46)) == []


def test_lembrete_constante_para_depois_de_24h(svc):
    _tarefa_com_lembrete(svc, insistir=60)
    assert svc.lembretes_vencidos(datetime(2026, 10, 27, 23, 0)) == []


def test_resumo_diario_uma_vez_por_dia(svc):
    hoje = date(2026, 10, 26)
    t = svc.adicionar_rapido("a")
    t.prazo = hoje
    svc.salvar(t)
    u = svc.adicionar_rapido("b")
    u.prazo = hoje - timedelta(days=2)
    svc.salvar(u)
    assert svc.resumo_diario(datetime(2026, 10, 26, 7, 59)) is None          # cedo demais
    r = svc.resumo_diario(datetime(2026, 10, 26, 8, 0))
    assert (r.hoje, r.atrasadas) == (1, 1)
    assert r.texto == "Você tem 1 tarefa para hoje e 1 atrasada."
    assert svc.resumo_diario(datetime(2026, 10, 26, 9, 0)) is None            # já avisou hoje
    assert svc.resumo_diario(datetime(2026, 10, 27, 8, 0)) is not None        # outro dia, avisa de novo


def test_resumo_diario_sem_tarefas_nao_avisa(svc):
    assert svc.resumo_diario(datetime(2026, 10, 26, 9, 0)) is None


# ---------- banco ----------
def test_migracao_para_versao_5_mantem_dados(tmp_path):
    import sqlite3
    arq = tmp_path / "v4.db"
    b = Banco(arq)
    s = Servico(b)
    t = s.adicionar_rapido("antiga")
    b.fechar()
    con = sqlite3.connect(arq)           # simula banco da versão 4 (sem as colunas novas)
    con.executescript("""
        CREATE TABLE tarefa_nova AS SELECT id, uuid, titulo, notas, projeto_id, pai_id, prioridade, prazo,
            prazo_hora, repeticao, lembretes, concluida_em, criada_em, atualizada_em, apagada_em, ordem FROM tarefa;
        DROP TABLE tarefa_tag; DROP TABLE notificacao; DROP TABLE soneca; DROP TABLE tarefa;
        ALTER TABLE tarefa_nova RENAME TO tarefa;
        PRAGMA user_version = 4;""")
    con.commit()
    con.close()
    b2 = Banco(arq)
    achada = b2.obter_tarefa_por_uuid(t.uuid)
    assert achada.titulo == "antiga" and achada.fixada is False and achada.insistir_min == 0
    assert b2.con.execute("PRAGMA user_version").fetchone()[0] == 6
