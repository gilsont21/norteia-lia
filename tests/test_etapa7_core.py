"""Etapa 7: calendário, períodos, matriz, ICS, importação e exportação."""
from datetime import date, datetime, time, timedelta

import pytest

from norteia.core import Banco, Servico
from norteia.core import calendario as cal
from norteia.core import exportacao, ics, matriz

HOJE = date(2026, 10, 26)      # segunda-feira


@pytest.fixture
def svc():
    return Servico(Banco(":memory:"))


def nova(svc, titulo, prazo=None, hora=None, **kw):
    t = svc.adicionar_rapido(titulo)
    t.prazo, t.prazo_hora = prazo, hora
    for k, v in kw.items():
        setattr(t, k, v)
    return svc.salvar(t)


# ---------------------------------------------------------------- períodos
def test_salvar_ajusta_periodo(svc):
    t = nova(svc, "a", HOJE, inicio=HOJE + timedelta(days=3))     # início depois do fim: troca
    assert t.inicio == HOJE and t.prazo == HOJE + timedelta(days=3)
    t.inicio = t.prazo
    assert svc.salvar(t).inicio is None                           # início = fim vira dia único
    t.prazo, t.inicio = None, HOJE
    assert svc.salvar(t).inicio is None                           # sem prazo não há período


def test_semana_comeca_no_domingo_ou_segunda():
    assert cal.inicio_da_semana(HOJE) == date(2026, 10, 25)
    assert cal.inicio_da_semana(HOJE, segunda_primeiro=True) == HOJE
    grade = cal.grade_do_mes(2026, 10)
    assert len(grade) == 42 and grade[0] == date(2026, 9, 27) and date(2026, 10, 31) in grade


# ---------------------------------------------------------------- ocorrências
def test_ocorrencias_simples_e_ordem(svc):
    nova(svc, "tarde", HOJE, time(15, 0))
    nova(svc, "manha", HOJE, time(8, 0))
    nova(svc, "dia inteiro", HOJE)
    nova(svc, "fora", HOJE + timedelta(days=30))
    oc = svc.calendario.ocorrencias(HOJE, HOJE)
    assert [o.titulo for o in oc] == ["dia inteiro", "manha", "tarde"]
    assert oc[1].duracao_min == 60 and oc[0].dia_inteiro and oc[1].fim_hora == time(9, 0)


def test_tarefa_de_varios_dias_aparece_em_cada_dia(svc):
    nova(svc, "viagem", HOJE + timedelta(days=2), inicio=HOJE)
    mapa = svc.calendario.por_dia(HOJE - timedelta(days=1), HOJE + timedelta(days=4))
    com = [d for d, itens in mapa.items() if itens]
    assert com == [HOJE, HOJE + timedelta(days=1), HOJE + timedelta(days=2)]
    assert svc.calendario.ocorrencias(HOJE, HOJE)[0].varios_dias


def test_repeticao_gera_ocorrencias_virtuais(svc):
    nova(svc, "academia", HOJE, time(7, 0), repeticao="FREQ=DAILY")
    oc = svc.calendario.ocorrencias(HOJE, HOJE + timedelta(days=3))
    assert [o.inicio for o in oc] == [HOJE + timedelta(days=i) for i in range(4)]
    assert [o.virtual for o in oc] == [False, True, True, True]
    assert not oc[1].editavel and oc[0].editavel


def test_repeticao_concluida_nao_duplica_com_a_proxima(svc):
    t = nova(svc, "semanal", HOJE, repeticao="FREQ=WEEKLY")
    svc.alternar_conclusao(t.id, HOJE)               # cria a próxima tarefa de verdade (semana que vem)
    oc = svc.calendario.ocorrencias(HOJE, HOJE + timedelta(days=14))
    datas = sorted(o.inicio for o in oc)
    assert datas == [HOJE, HOJE + timedelta(days=7), HOJE + timedelta(days=14)]
    assert sum(o.concluida for o in oc) == 1


def test_calendario_ignora_lixeira_e_lista_arquivada(svc):
    p = svc.criar_projeto("Velha")
    a = nova(svc, "na lixeira", HOJE)
    svc.apagar(a.id)
    b = nova(svc, "arquivada", HOJE, projeto_id=p.id)
    nova(svc, "ok", HOJE)
    svc.arquivar_projeto(p.id)
    assert [o.titulo for o in svc.calendario.ocorrencias(HOJE, HOJE)] == ["ok"]
    assert b.id


def test_excluir_finalizadas_do_calendario(svc):
    t = nova(svc, "feita", HOJE)
    svc.alternar_conclusao(t.id)
    assert len(svc.calendario.ocorrencias(HOJE, HOJE)) == 1
    assert svc.calendario.ocorrencias(HOJE, HOJE, incluir_finalizadas=False) == []


def test_agenda_mostra_so_dias_com_itens(svc):
    nova(svc, "a", HOJE)
    nova(svc, "b", HOJE + timedelta(days=5))
    ag = svc.calendario.agenda(HOJE, 10)
    assert [d for d, _ in ag] == [HOJE, HOJE + timedelta(days=5)]


def test_mover_para_outro_dia_e_hora(svc):
    t = nova(svc, "a", HOJE, time(9, 0))
    cal.mover_para(svc, t.id, HOJE + timedelta(days=2))
    m = svc.banco.obter_tarefa(t.id)
    assert m.prazo == HOJE + timedelta(days=2) and m.prazo_hora == time(9, 0)    # hora mantida
    cal.mover_para(svc, t.id, HOJE, time(14, 30))
    assert svc.banco.obter_tarefa(t.id).prazo_hora == time(14, 30)
    cal.mover_para(svc, t.id, HOJE, None)
    assert svc.banco.obter_tarefa(t.id).prazo_hora is None


def test_mover_tarefa_de_varios_dias_mantem_a_duracao(svc):
    t = nova(svc, "viagem", HOJE + timedelta(days=2), inicio=HOJE)
    cal.mover_para(svc, t.id, HOJE + timedelta(days=10))
    m = svc.banco.obter_tarefa(t.id)
    assert m.inicio == HOJE + timedelta(days=10) and m.prazo == HOJE + timedelta(days=12)


def test_definir_periodo_e_duracao(svc):
    t = nova(svc, "a", HOJE)
    cal.definir_periodo(svc, t.id, HOJE + timedelta(days=3), HOJE)      # invertido: arruma
    m = svc.banco.obter_tarefa(t.id)
    assert m.inicio == HOJE and m.prazo == HOJE + timedelta(days=3)
    cal.definir_duracao(svc, t.id, 5)
    assert svc.banco.obter_tarefa(t.id).duracao_min == 15                # mínimo de 15 minutos
    cal.definir_duracao(svc, t.id, 90)
    assert svc.banco.obter_tarefa(t.id).duracao_min == 90


def test_proxima_ocorrencia_mantem_periodo(svc):
    t = nova(svc, "plantão", HOJE + timedelta(days=1), inicio=HOJE, repeticao="FREQ=WEEKLY", secao="Fixos",
             duracao_min=120)
    svc.alternar_conclusao(t.id, HOJE)
    nova_t = [x for x in svc.banco.consultar("concluida_em IS NULL")][0]
    assert nova_t.prazo - nova_t.inicio == timedelta(days=1) and nova_t.secao == "Fixos"
    assert nova_t.duracao_min == 120


def test_duplicar_copia_campos_novos(svc):
    t = nova(svc, "a", HOJE + timedelta(days=1), inicio=HOJE, secao="X", duracao_min=30)
    c = svc.duplicar(t.id)
    assert (c.inicio, c.secao, c.duracao_min) == (HOJE, "X", 30)


def test_nota_nao_se_conclui(svc):
    n = svc.criar_nota("ideia")
    assert n.eh_nota and svc.alternar_conclusao(n.id).concluida_em is None
    with pytest.raises(ValueError):
        svc.criar_nota("  ")


def test_migracao_v6_preserva_dados(tmp_path):
    import sqlite3
    arq = tmp_path / "v5.db"
    b = Banco(arq)
    b.con.execute("DROP TABLE registro")
    b.con.commit()
    b.fechar()
    con = sqlite3.connect(arq)
    con.execute("ALTER TABLE tarefa DROP COLUMN secao")
    con.execute("ALTER TABLE projeto DROP COLUMN pasta")
    con.execute("PRAGMA user_version = 5")
    con.commit()
    con.close()
    b2 = Banco(arq)
    t = b2.salvar_tarefa(__import__("norteia.core.models", fromlist=["Tarefa"]).Tarefa("x", secao="S"))
    assert b2.obter_tarefa(t.id).secao == "S"
    assert b2.con.execute("PRAGMA user_version").fetchone()[0] == 6


# ---------------------------------------------------------------- seções do Kanban
def test_secoes_ordem_e_em_uso(svc):
    p = svc.criar_projeto("Proj")
    svc.banco.definir_secoes(p.id, ["Fazendo", "Feito", "Fazendo", " "])
    nova(svc, "a", projeto_id=p.id, secao="Revisão")
    assert svc.banco.secoes_da_lista(p.id) == ["Fazendo", "Feito", "Revisão"]
    assert svc.banco.secoes_da_lista(None) == []
    svc.banco.definir_secoes(None, ["Caixa1"])
    assert svc.banco.secoes_da_lista(None) == ["Caixa1"]


# ---------------------------------------------------------------- matriz
def test_matriz_quadrantes(svc):
    nova(svc, "q1", HOJE, prioridade=3)
    nova(svc, "q2", HOJE + timedelta(days=10), prioridade=2)
    nova(svc, "q3", HOJE - timedelta(days=1))
    nova(svc, "q4")
    nota = svc.criar_nota("nota fora da matriz")
    q = svc.matriz.quadrantes(HOJE)
    assert [t.titulo for t in q["q1"]] == ["q1"] and [t.titulo for t in q["q2"]] == ["q2"]
    assert [t.titulo for t in q["q3"]] == ["q3"] and [t.titulo for t in q["q4"]] == ["q4"]
    assert nota.id not in [t.id for lista in q.values() for t in lista]


@pytest.mark.parametrize("origem,destino", [("q4", "q1"), ("q1", "q4"), ("q3", "q2"), ("q2", "q3"), ("q1", "q2")])
def test_matriz_mover_leva_para_o_quadrante(svc, origem, destino):
    dados = {"q1": (HOJE, 3), "q2": (HOJE + timedelta(days=10), 2), "q3": (HOJE, 0), "q4": (None, 0)}
    prazo, prio = dados[origem]
    t = nova(svc, "x", prazo, prioridade=prio)
    svc.matriz.mover(t.id, destino, HOJE)
    assert matriz.quadrante(svc.banco.obter_tarefa(t.id), HOJE) == destino


# ---------------------------------------------------------------- ICS
ICS_EXEMPLO = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1@x
SUMMARY:Reunião\\, com vírgula
DESCRIPTION:Linha 1\\nLinha 2
LOCATION:Sala 3
DTSTART:20261104T130000Z
DTEND:20261104T140000Z
RRULE:FREQ=WEEKLY;UNTIL=20261231T000000Z
BEGIN:VALARM
TRIGGER:-PT15M
ACTION:DISPLAY
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:2@x
SUMMARY:Feriado
DTSTART;VALUE=DATE:20261115
DTEND;VALUE=DATE:20261116
END:VEVENT
BEGIN:VEVENT
UID:3@x
SUMMARY:Conferência
DTSTART;TZID=America/Sao_Paulo:20261110T090000
DTEND;TZID=America/Sao_Paulo:20261112T180000
END:VEVENT
BEGIN:VTODO
UID:4@x
SUMMARY:Entregar relatório
DUE;VALUE=DATE:20261120
PRIORITY:1
END:VTODO
END:VCALENDAR
"""


def test_ler_ics():
    from dateutil import tz
    ev = ics.ler_ics(ICS_EXEMPLO, tz.gettz("America/Sao_Paulo"))
    assert [e.titulo for e in ev] == ["Reunião, com vírgula", "Feriado", "Conferência", "Entregar relatório"]
    a, b, c, d = ev
    assert a.inicio == datetime(2026, 11, 4, 10, 0)            # 13:00Z = 10:00 em São Paulo (UTC-3)
    assert a.descricao == "Linha 1\nLinha 2" and a.local == "Sala 3" and a.lembretes == [15]
    assert "UNTIL=20261231T000000" in a.regra and not a.regra.endswith("Z")
    assert b.dia_inteiro and b.dias() == (date(2026, 11, 15), date(2026, 11, 15))   # DTEND exclusivo
    assert c.inicio == datetime(2026, 11, 10, 9, 0) and c.dias() == (date(2026, 11, 10), date(2026, 11, 12))
    assert d.tipo == "VTODO" and d.prioridade == 3


def test_ocorrencias_de_evento_repetido():
    from dateutil import tz
    a = ics.ler_ics(ICS_EXEMPLO, tz.gettz("America/Sao_Paulo"))[0]
    dias = ics.ocorrencias_do_evento(a, date(2026, 11, 1), date(2026, 11, 30))
    assert [d for d, _ in dias] == [date(2026, 11, 4), date(2026, 11, 11), date(2026, 11, 18), date(2026, 11, 25)]
    assert ics.ocorrencias_do_evento(a, date(2027, 2, 1), date(2027, 2, 28)) == []     # depois do UNTIL


def test_escrever_e_reler_ics(svc):
    t = nova(svc, "Prova; final, geral", HOJE, time(19, 30), repeticao="FREQ=WEEKLY", lembretes=[30],
             notas="levar\ncalculadora", prioridade=3, tags=["si601"], duracao_min=120)
    nova(svc, "Viagem", HOJE + timedelta(days=2), inicio=HOJE)
    texto = exportacao.exportar_ics(svc)
    assert texto.startswith("BEGIN:VCALENDAR") and "\r\n" in texto and "RRULE:FREQ=WEEKLY" in texto
    assert all(len(l.encode()) <= 75 for l in texto.split("\r\n"))
    assert "DTEND;VALUE=DATE:" + (HOJE + timedelta(days=3)).strftime("%Y%m%d") in texto
    volta = ics.ler_ics(texto)
    prova = next(e for e in volta if e.titulo.startswith("Prova"))
    assert prova.titulo == "Prova; final, geral" and prova.inicio == datetime.combine(HOJE, time(19, 30))
    assert prova.fim == datetime.combine(HOJE, time(21, 30)) and prova.lembretes == [30]
    assert prova.prioridade == 3 and prova.descricao == "levar\ncalculadora"
    assert t.id


def test_exportar_ics_pula_concluidas_e_sem_data(svc):
    a = nova(svc, "feita", HOJE)
    svc.alternar_conclusao(a.id)
    nova(svc, "sem data")
    assert "SUMMARY" not in exportacao.exportar_ics(svc)
    assert "SUMMARY:✓ feita" in exportacao.exportar_ics(svc, incluir_finalizadas=True)


def test_importar_ics(svc):
    from dateutil import tz
    r = exportacao.importar_ics(svc, ICS_EXEMPLO, tz_destino=tz.gettz("America/Sao_Paulo"))
    assert r.tarefas == 4
    por_titulo = {t.titulo: t for t in svc.banco.consultar()}
    reun = por_titulo["Reunião, com vírgula"]
    assert reun.prazo == date(2026, 11, 4) and reun.prazo_hora == time(10, 0) and reun.duracao_min == 60
    assert reun.repeticao.startswith("FREQ=WEEKLY") and reun.lembretes == [15] and "Sala 3" in reun.notas
    conf = por_titulo["Conferência"]
    assert conf.inicio == date(2026, 11, 10) and conf.prazo == date(2026, 11, 12)
    assert por_titulo["Feriado"].prazo_hora is None and int(por_titulo["Entregar relatório"].prioridade) == 3


# ---------------------------------------------------------------- assinaturas
def test_assinatura_alimenta_o_calendario(svc):
    from dateutil import tz
    aid = svc.assin.adicionar("Google", "webcal://calendar.example/x.ics")
    assert svc.assin.listar()[0]["url"] == "https://calendar.example/x.ics"
    assert svc.assin.aplicar_texto(aid, ICS_EXEMPLO, tz.gettz("America/Sao_Paulo")) == 3     # tarefas VTODO não entram
    oc = svc.calendario.ocorrencias(date(2026, 11, 1), date(2026, 11, 30))
    ext = [o for o in oc if o.externo]
    assert sorted({o.titulo for o in ext}) == ["Conferência", "Feriado", "Reunião, com vírgula"]
    assert sum(o.titulo.startswith("Reunião") for o in ext) == 4          # semanal até o fim do mês
    assert all(not o.editavel for o in ext)
    assert svc.calendario.ocorrencias(date(2026, 11, 1), date(2026, 11, 30), externos=False) == []
    svc.assin.remover(aid)
    assert svc.calendario.ocorrencias(date(2026, 11, 1), date(2026, 11, 30)) == []


def test_assinatura_exige_endereco_valido(svc):
    from norteia.core.assinaturas import ErroAssinatura
    with pytest.raises(ErroAssinatura):
        svc.assin.adicionar("x", "ftp://exemplo")


# ---------------------------------------------------------------- backup e CSV
def test_backup_json_ida_e_volta(svc):
    p = svc.criar_projeto("Faculdade")
    t = svc.adicionar_rapido("Estudar #si601 !3 amanhã", projeto_id=p.id)
    svc.adicionar_subtarefa(t.id, "capítulo 1")
    h = svc.habitos.criar("Beber água", meta=8)
    svc.habitos.definir_quantidade(h, HOJE, 8)
    texto = exportacao.exportar_json(svc)
    outro = Servico(Banco(":memory:"))
    r = exportacao.importar_json(outro, texto)
    assert r.tarefas == 2 and r.listas == 1
    assert [x.titulo for x in outro.banco.consultar("pai_id IS NULL")] == ["Estudar"]
    assert outro.habitos.listar()[0].nome == "Beber água"
    assert outro.habitos.quantidade(outro.habitos.listar()[0], HOJE) == 8
    exportacao.importar_json(outro, texto)                        # importar de novo não duplica
    assert len(outro.banco.consultar()) == 2


def test_backup_invalido(svc):
    with pytest.raises(ValueError):
        exportacao.importar_json(svc, "isto não é json")
    with pytest.raises(ValueError):
        exportacao.importar_json(svc, '{"formato": "outro"}')


def test_csv_proprio_ida_e_volta(svc):
    p = svc.criar_projeto("Casa")
    t = nova(svc, "Pagar luz", HOJE, time(9, 0), projeto_id=p.id, prioridade=3, tags=["contas"],
             repeticao="FREQ=MONTHLY", lembretes=[0, 60], notas="conta; vence dia 10")
    svc.adicionar_subtarefa(t.id, "pegar boleto")
    texto = exportacao.exportar_csv(svc)
    assert texto.startswith("﻿Lista;Título")
    outro = Servico(Banco(":memory:"))
    r = exportacao.importar_csv(outro, texto)
    assert r.tarefas == 1 and r.subtarefas == 1 and r.listas == 1
    pai = outro.banco.consultar("pai_id IS NULL")[0]
    assert (pai.titulo, pai.prazo, pai.prazo_hora, int(pai.prioridade)) == ("Pagar luz", HOJE, time(9, 0), 3)
    assert pai.tags == ["contas"] and pai.repeticao == "FREQ=MONTHLY" and pai.lembretes == [0, 60]
    assert pai.notas == "conta; vence dia 10"
    assert [s.titulo for s in outro.subtarefas(pai.id)] == ["pegar boleto"]


CSV_OUTRO_APP = '''"Date: 2026-10-20+0000"
"Version: 6.0.2.0"
"Status: 0 Normal; 1 Completed; 2 Archived"
"Folder Name","List Name","Title","Kind","Tags","Content","Is Check list","Start Date","Due Date","Reminder","Repeat","Priority","Status","Created Time","Completed Time","Order","Timezone","Is All Day","Is Floating","Column Name","Column Order","View Mode","taskId","parentId"
"Estudos","Faculdade","Estudar índices","TEXT","si601, prova final","Rever árvores B","N","2026-11-02T17:00:00+0000","2026-11-02T17:00:00+0000","TRIGGER:-PT30M","FREQ=WEEKLY;INTERVAL=1;TT_SKIP=HOLIDAY","5","0","2026-10-01T12:00:00+0000","","1","America/Sao_Paulo","false","false","Fazendo","0","list","1",""
"","Faculdade","Passo 1","TEXT","","","N","","","","","0","1","2026-10-01T12:00:00+0000","2026-10-02T12:00:00+0000","2","America/Sao_Paulo","false","false","","","list","2","1"
"","Inbox","Compras","TEXT","","▫Leite\n▪Pão\nobs","Y","","2026-11-05T03:00:00+0000","","","1","0","2026-10-01T12:00:00+0000","","3","America/Sao_Paulo","true","false","","","list","3",""
"","Inbox","Ideia solta","NOTE","","texto da nota","N","","","","","0","0","2026-10-01T12:00:00+0000","","4","America/Sao_Paulo","false","false","","","list","4",""
"","Inbox","Desistiu","TEXT","","","N","","","","","0","-1","2026-10-01T12:00:00+0000","","5","America/Sao_Paulo","false","false","","","list","5",""
"","Inbox","","TEXT","","","N","","","","","0","0","","","","","","","","","list","6",""
'''


def test_importar_backup_de_outro_app(svc):
    r = exportacao.importar_csv(svc, CSV_OUTRO_APP)
    assert r.listas == 1 and r.ignoradas == 1
    todas = {t.titulo: t for t in svc.banco.consultar()}
    estudar = todas["Estudar índices"]
    assert estudar.prazo == date(2026, 11, 2) and estudar.prazo_hora == time(14, 0)       # 17:00Z em São Paulo
    assert int(estudar.prioridade) == 3 and estudar.tags == ["prova-final", "si601"]
    assert estudar.lembretes == [30] and estudar.repeticao == "FREQ=WEEKLY;INTERVAL=1"   # TT_SKIP removido
    assert estudar.secao == "Fazendo" and estudar.notas == "Rever árvores B"
    assert svc.banco.obter_projeto(estudar.projeto_id).nome == "Faculdade"
    assert svc.banco.obter_projeto(estudar.projeto_id).pasta == "Estudos"
    passo = todas["Passo 1"]
    assert passo.pai_id == estudar.id and passo.concluida and passo.projeto_id == estudar.projeto_id
    compras = todas["Compras"]
    assert compras.projeto_id is None and compras.prazo == date(2026, 11, 5) and compras.prazo_hora is None
    assert [(s.titulo, s.concluida) for s in svc.subtarefas(compras.id)] == [("Leite", False), ("Pão", True)]
    assert compras.notas == "obs" and int(compras.prioridade) == 1
    assert todas["Ideia solta"].eh_nota and todas["Desistiu"].descartada


def test_csv_sem_cabecalho_da_erro(svc):
    with pytest.raises(ValueError):
        exportacao.importar_csv(svc, "a,b\n1,2\n")


# ---------------------------------------------------------------- kanban
from norteia.core import kanban


def test_kanban_por_secao_e_mover(svc):
    p = svc.criar_projeto("Proj")
    kanban.criar_secao(svc, p.id, "Fazendo")
    kanban.criar_secao(svc, p.id, "Feito")
    a = nova(svc, "a", projeto_id=p.id, secao="Fazendo")
    b = nova(svc, "b", projeto_id=p.id)
    cols = kanban.colunas(svc, "secao", svc.listar(p.id), p.id)
    assert [(c.titulo, [t.titulo for t in c.tarefas]) for c in cols] == [
        ("Sem seção", ["b"]), ("Fazendo", ["a"]), ("Feito", [])]
    kanban.mover(svc, b.id, "secao", "Feito")
    assert svc.banco.obter_tarefa(b.id).secao == "Feito"
    kanban.mover(svc, a.id, "secao", "")
    assert svc.banco.obter_tarefa(a.id).secao == ""


def test_kanban_secoes_renomear_apagar_mover(svc):
    p = svc.criar_projeto("Proj")
    for n in ("A", "B", "C"):
        kanban.criar_secao(svc, p.id, n)
    kanban.criar_secao(svc, p.id, "A")                         # repetida: ignora
    t = nova(svc, "t", projeto_id=p.id, secao="B")
    kanban.renomear_secao(svc, p.id, "B", "Bravo")
    assert svc.banco.secoes_da_lista(p.id) == ["A", "Bravo", "C"] and svc.banco.obter_tarefa(t.id).secao == "Bravo"
    kanban.mover_secao(svc, p.id, "Bravo", -1)
    assert svc.banco.secoes_da_lista(p.id) == ["Bravo", "A", "C"]
    kanban.mover_secao(svc, p.id, "Bravo", -1)                 # já é a primeira: nada muda
    assert svc.banco.secoes_da_lista(p.id)[0] == "Bravo"
    kanban.apagar_secao(svc, p.id, "Bravo")
    assert svc.banco.secoes_da_lista(p.id) == ["A", "C"] and svc.banco.obter_tarefa(t.id).secao == ""
    with pytest.raises(ValueError):
        kanban.criar_secao(svc, p.id, " ")


def test_kanban_secoes_da_caixa_de_entrada(svc):
    kanban.criar_secao(svc, None, "Hoje não")
    t = nova(svc, "x", secao="Hoje não")
    cols = kanban.colunas(svc, "secao", svc.listar("caixa"), None)
    assert [c.titulo for c in cols] == ["Sem seção", "Hoje não"] and cols[1].tarefas[0].id == t.id


def test_kanban_modo_valido():
    assert kanban.modo_valido("secao", 3) == "secao" and kanban.modo_valido("secao", "caixa") == "secao"
    assert kanban.modo_valido("secao", "hoje") == "data" and kanban.modo_valido("prioridade", "hoje") == "prioridade"


def test_kanban_por_data(svc):
    nova(svc, "atrasada", HOJE - timedelta(days=2))
    nova(svc, "hoje", HOJE)
    nova(svc, "amanha", HOJE + timedelta(days=1))
    nova(svc, "semana", HOJE + timedelta(days=5))
    nova(svc, "longe", HOJE + timedelta(days=40))
    nova(svc, "sem")
    cols = kanban.colunas(svc, "data", svc.listar("todas", HOJE), hoje=HOJE)
    assert [(c.chave, [t.titulo for t in c.tarefas]) for c in cols] == [
        ("atrasadas", ["atrasada"]), ("hoje", ["hoje"]), ("amanha", ["amanha"]), ("semana", ["semana"]),
        ("depois", ["longe"]), ("sem", ["sem"])]
    assert [c.aceita_soltar for c in cols] == [False, True, True, True, True, True]


def test_kanban_mover_por_data(svc):
    t = nova(svc, "x", HOJE + timedelta(days=9), time(10, 0), lembretes=[0], repeticao="FREQ=DAILY")
    kanban.mover(svc, t.id, "data", "amanha", HOJE)
    assert svc.banco.obter_tarefa(t.id).prazo == HOJE + timedelta(days=1)
    kanban.mover(svc, t.id, "data", "sem", HOJE)
    m = svc.banco.obter_tarefa(t.id)
    assert m.prazo is None and m.prazo_hora is None and m.lembretes == [] and m.repeticao is None
    with pytest.raises(ValueError):
        kanban.mover(svc, t.id, "data", "atrasadas", HOJE)


def test_kanban_mover_por_data_mantem_periodo(svc):
    t = nova(svc, "x", HOJE + timedelta(days=3), inicio=HOJE + timedelta(days=1))
    kanban.mover(svc, t.id, "data", "depois", HOJE)
    m = svc.banco.obter_tarefa(t.id)
    assert m.prazo == HOJE + timedelta(days=30) and m.prazo - m.inicio == timedelta(days=2)


def test_kanban_prioridade_e_lista(svc):
    p = svc.criar_projeto("Proj")
    t = nova(svc, "x")
    sub = svc.adicionar_subtarefa(t.id, "sub")
    kanban.mover(svc, t.id, "prioridade", 3)
    assert int(svc.banco.obter_tarefa(t.id).prioridade) == 3
    kanban.mover(svc, t.id, "projeto", p.id)
    assert svc.banco.obter_tarefa(sub.id).projeto_id == p.id                  # subtarefa acompanha
    cols = kanban.colunas(svc, "projeto", svc.listar("todas"))
    assert [(c.titulo, len(c.tarefas)) for c in cols] == [("Caixa de Entrada", 0), ("Proj", 1)]
    cols = kanban.colunas(svc, "prioridade", svc.listar("todas"))
    assert [(c.titulo, len(c.tarefas)) for c in cols] == [("Alta", 1), ("Média", 0), ("Baixa", 0), ("Nenhuma", 0)]
    with pytest.raises(ValueError):
        kanban.colunas(svc, "xyz", [])


# ---------------------------------------------------------------- repetição personalizada
from norteia.core import recorrencia


def test_construir_e_analisar_regra():
    r = recorrencia.construir("WEEKLY", 2, [0, 2], ate=date(2026, 12, 31))
    assert r == "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE;UNTIL=20261231T235959"
    assert recorrencia.analisar(r) == {"freq": "WEEKLY", "intervalo": 2, "dias": [0, 2],
                                       "ate": date(2026, 12, 31), "vezes": None}
    assert recorrencia.construir("DAILY") == "FREQ=DAILY"
    assert recorrencia.construir("MONTHLY", 1, [3], vezes=5) == "FREQ=MONTHLY;COUNT=5"      # dias só em semanal
    assert recorrencia.construir("YEARLY", 1, None, ate=date(2030, 1, 1), vezes=3).endswith("UNTIL=20300101T235959")
    with pytest.raises(ValueError):
        recorrencia.construir("HOURLY")
    assert recorrencia.valida(r)


def test_analisar_regra_nao_suportada():
    assert recorrencia.analisar("FREQ=MONTHLY;BYMONTHDAY=15") is None
    assert recorrencia.analisar("FREQ=MONTHLY;BYDAY=1MO") is None
    assert recorrencia.analisar(None) is None and recorrencia.analisar("lixo") is None


def test_descrever_com_fim():
    assert recorrencia.descrever("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE;COUNT=5") == "A cada 2 semanas (seg, qua), 5 vezes"
    assert recorrencia.descrever("FREQ=DAILY;UNTIL=20261231T235959") == "A cada dia, até 31/12/2026"
    assert recorrencia.descrever("FREQ=DAILY;COUNT=1") == "A cada dia, 1 vez"


def test_repeticao_com_contagem_termina(svc):
    t = nova(svc, "só 3 vezes", HOJE, repeticao="FREQ=DAILY;COUNT=3")
    svc.alternar_conclusao(t.id, HOJE)
    segunda = svc.banco.consultar("concluida_em IS NULL")[0]
    assert segunda.repeticao == "FREQ=DAILY;COUNT=2" and segunda.prazo == HOJE + timedelta(days=1)
    svc.alternar_conclusao(segunda.id, HOJE)
    terceira = svc.banco.consultar("concluida_em IS NULL")[0]
    assert terceira.repeticao == "FREQ=DAILY;COUNT=1"
    svc.alternar_conclusao(terceira.id, HOJE)
    assert svc.banco.consultar("concluida_em IS NULL") == []              # acabou


def test_repeticao_com_data_final_termina(svc):
    t = nova(svc, "até amanhã", HOJE, repeticao="FREQ=DAILY;UNTIL=" + (HOJE + timedelta(days=1)).strftime("%Y%m%d") + "T235959")
    svc.alternar_conclusao(t.id, HOJE)
    segunda = svc.banco.consultar("concluida_em IS NULL")[0]
    svc.alternar_conclusao(segunda.id, HOJE)
    assert svc.banco.consultar("concluida_em IS NULL") == []


def test_calendario_respeita_contagem(svc):
    nova(svc, "3 vezes", HOJE, repeticao="FREQ=DAILY;COUNT=3")
    assert len(svc.calendario.ocorrencias(HOJE, HOJE + timedelta(days=10))) == 3
