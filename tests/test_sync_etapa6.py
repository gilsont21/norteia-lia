from tests.test_sync import mundo  # noqa: F401  (reaproveita a fixture "dois aparelhos + servidor")


def test_campos_novos_atravessam_a_sincronizacao(mundo):
    pc, sync_pc, cel, sync_cel, *_ = mundo
    t = pc.adicionar_rapido("Reunião hoje às 10h")
    t.insistir_min = 10
    pc.salvar(t)
    pc.alternar_fixada(t.id)
    outra = pc.adicionar_rapido("Desistir")
    pc.alternar_descarte(outra.id)
    sync_pc.sincronizar()
    sync_cel.sincronizar()
    a = cel.banco.obter_tarefa_por_uuid(t.uuid)
    b = cel.banco.obter_tarefa_por_uuid(outra.uuid)
    assert a.fixada and a.insistir_min == 10
    assert b.descartada


def test_projeto_renomeado_arquivado_e_apagado_chega_ao_outro_aparelho(mundo):
    pc, sync_pc, cel, sync_cel, *_ = mundo
    p = pc.criar_projeto("Casa")
    t = pc.adicionar_rapido("trocar lâmpada", p.id)
    sync_pc.sincronizar()
    sync_cel.sincronizar()

    pc.renomear_projeto(p.id, "Apartamento")
    pc.arquivar_projeto(p.id)
    sync_pc.sincronizar()
    sync_cel.sincronizar()
    no_cel = cel.banco.obter_projeto_por_uuid(p.uuid)
    assert no_cel.nome == "Apartamento" and no_cel.arquivado

    pc.arquivar_projeto(p.id, False)
    pc.apagar_projeto(p.id)
    sync_pc.sincronizar()
    sync_cel.sincronizar()
    assert cel.banco.obter_projeto_por_uuid(p.uuid).apagado_em is not None
    assert cel.banco.obter_tarefa_por_uuid(t.uuid).apagada_em is not None


def test_renomear_etiqueta_chega_pelas_tarefas(mundo):
    pc, sync_pc, cel, sync_cel, *_ = mundo
    t = pc.adicionar_rapido("a #prova")
    sync_pc.sincronizar()
    sync_cel.sincronizar()
    pc.renomear_tag("prova", "exame")
    sync_pc.sincronizar()
    sync_cel.sincronizar()
    assert cel.banco.obter_tarefa_por_uuid(t.uuid).tags == ["exame"]


def test_cliente_antigo_sem_campos_novos_ainda_e_aceito(mundo):
    """Um pacote sem fixada/descartada_em/insistir_min (aparelho de versão anterior) não quebra."""
    from norteia.sync.serial import aplicar, empacotar
    pc, _sync_pc, cel, _sync_cel, *_ = mundo
    t = pc.adicionar_rapido("velha")
    pacote = empacotar(pc.banco)
    for d in pacote["tarefas"]:
        for k in ("fixada", "descartada_em", "insistir_min"):
            d.pop(k)
    aplicar(cel.banco, pacote)
    nova = cel.banco.obter_tarefa_por_uuid(t.uuid)
    assert not nova.fixada and not nova.descartada and nova.insistir_min == 0
