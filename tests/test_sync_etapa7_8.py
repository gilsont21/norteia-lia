from datetime import date, datetime, timedelta

from tests.test_sync import mundo  # noqa: F401  (reaproveita a fixture "dois aparelhos + servidor")

from norteia.core.foco import Sessao


def test_campos_da_etapa_7_atravessam(mundo):
    pc, sync_pc, cel, sync_cel, *_ = mundo
    t = pc.adicionar_rapido("Projeto longo")
    t.inicio, t.prazo, t.duracao_min, t.secao, t.tipo = (date(2026, 11, 2), date(2026, 11, 9), 90, "Fazendo", "nota")
    pc.salvar(t)
    p = pc.criar_projeto("Faculdade")
    pc.definir_pasta_projeto(p.id, "Semestre")
    sync_pc.sincronizar()
    sync_cel.sincronizar()
    b = cel.banco.obter_tarefa_por_uuid(t.uuid)
    assert (b.inicio, b.prazo, b.duracao_min, b.secao, b.tipo) == (date(2026, 11, 2), date(2026, 11, 9), 90,
                                                                    "Fazendo", "nota")
    assert cel.banco.obter_projeto_por_uuid(p.uuid).pasta == "Semestre"


def test_habitos_marcacoes_foco_e_contagens_sincronizam(mundo):
    pc, sync_pc, cel, sync_cel, *_ = mundo
    hoje = date.today()
    h = pc.habitos.criar("Beber água", meta=3)
    pc.habitos.definir_quantidade(h, hoje, 2)
    pc.foco.registrar(Sessao(datetime.now().replace(microsecond=0), 1500))
    pc.contagens_regressivas.criar("Prova", hoje + timedelta(days=5))
    t = pc.adicionar_rapido("Com comentário")
    pc.comentarios.adicionar(t.id, "lembrar do edital")
    pc.modelos.salvar_de_tarefa(t.id, "Modelo A")
    sync_pc.sincronizar()
    sync_cel.sincronizar()
    h2 = cel.habitos.obter(h.uuid)
    assert h2 is not None and h2.meta == 3 and cel.habitos.quantidade(h2, hoje) == 2
    assert [s.duracao_s for s in cel.foco.sessoes()] == [1500]
    assert [c.nome for c in cel.contagens_regressivas.listar()] == ["Prova"]
    t2 = cel.banco.obter_tarefa_por_uuid(t.uuid)
    assert [c.texto for c in cel.comentarios.listar(t2.id)] == ["lembrar do edital"]
    assert [m.nome for m in cel.modelos.listar()] == ["Modelo A"]


def test_marcar_o_mesmo_dia_nos_dois_aparelhos_nao_duplica(mundo):
    pc, sync_pc, cel, sync_cel, *_ = mundo
    hoje = date.today()
    h = pc.habitos.criar("Ler")
    sync_pc.sincronizar()
    sync_cel.sincronizar()
    h_cel = cel.habitos.obter(h.uuid)
    pc.habitos.alternar(h, hoje)
    cel.habitos.alternar(h_cel, hoje)
    for s in (sync_pc, sync_cel, sync_pc):
        s.sincronizar()
    assert len(pc.banco.listar_registros("marcacao")) == 1
    assert len(cel.banco.listar_registros("marcacao")) == 1
    assert pc.habitos.concluido(h, hoje) == cel.habitos.concluido(h_cel, hoje)


def test_apagar_habito_chega_ao_outro_aparelho(mundo):
    pc, sync_pc, cel, sync_cel, *_ = mundo
    h = pc.habitos.criar("Temporário")
    sync_pc.sincronizar()
    sync_cel.sincronizar()
    assert cel.habitos.obter(h.uuid) is not None
    pc.habitos.apagar(h.uuid)
    sync_pc.sincronizar()
    sync_cel.sincronizar()
    assert cel.habitos.obter(h.uuid) is None


def test_cor_da_etiqueta_sincroniza(mundo):
    pc, sync_pc, cel, sync_cel, *_ = mundo
    pc.adicionar_rapido("a #prova")
    pc.definir_cor_tag("prova", "#f5a623")
    sync_pc.sincronizar()
    sync_cel.sincronizar()
    assert {g.nome: g.cor for g in cel.banco.listar_tags()}["prova"] == "#f5a623"
