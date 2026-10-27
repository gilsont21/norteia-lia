from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from norteia.core import Banco, Servico
from norteia.core.models import agora_utc
from norteia.sync import Sincronizador
from norteia.sync.servidor import criar_app

TOKEN = "senha-de-teste-123"


@pytest.fixture
def mundo():
    """Servidor + dois aparelhos (celular e computador), tudo em memória."""
    servidor = Banco(":memory:", varias_threads=True)
    http = TestClient(criar_app(servidor, TOKEN))

    def aparelho():
        banco = Banco(":memory:")
        def transporte(caminho, corpo):
            r = http.post(caminho, json=corpo, headers={"Authorization": f"Bearer {TOKEN}"})
            r.raise_for_status()
            return r.json()
        return Servico(banco), Sincronizador(banco, transporte)

    pc, sync_pc = aparelho()
    celular, sync_cel = aparelho()
    return pc, sync_pc, celular, sync_cel, servidor, http


def titulos(svc):
    return sorted(t.titulo for t in svc.banco.consultar("apagada_em IS NULL AND pai_id IS NULL"))


def test_tarefa_criada_no_pc_chega_ao_celular(mundo):
    pc, sync_pc, cel, sync_cel, *_ = mundo
    p = pc.criar_projeto("Faculdade")
    t = pc.adicionar_rapido("Estudar #si601 !3 amanhã às 14h", projeto_id=p.id)
    assert sync_pc.sincronizar().enviados >= 2
    r = sync_cel.sincronizar()
    assert r.recebidos == 2
    nova = cel.banco.obter_tarefa_por_uuid(t.uuid)
    assert nova.titulo == "Estudar" and nova.tags == ["si601"] and int(nova.prioridade) == 3
    assert nova.prazo_hora == t.prazo_hora and nova.lembretes == [0]
    assert cel.banco.obter_projeto(nova.projeto_id).nome == "Faculdade"


def test_ida_e_volta_sem_eco(mundo):
    pc, sync_pc, cel, sync_cel, *_ = mundo
    pc.adicionar_rapido("A")
    sync_pc.sincronizar()
    sync_cel.sincronizar()
    # nada mudou: as próximas rodadas não devem enviar nem receber nada
    assert sync_cel.sincronizar().enviados == 0
    r = sync_pc.sincronizar()
    assert r.recebidos == 0 and r.enviados == 0


def test_conflito_vale_a_edicao_mais_recente(mundo):
    pc, sync_pc, cel, sync_cel, *_ = mundo
    t = pc.adicionar_rapido("Original")
    sync_pc.sincronizar(); sync_cel.sincronizar()
    # o celular edita primeiro, o PC edita depois (relógio do PC mais novo)
    c = cel.banco.obter_tarefa_por_uuid(t.uuid)
    c.titulo = "Editado no celular"
    cel.salvar(c)
    p = pc.banco.obter_tarefa(t.id)
    p.titulo = "Editado no PC"
    pc.salvar(p)
    p.atualizada_em = c.atualizada_em + timedelta(seconds=5)
    pc.banco.salvar_tarefa(p, preservar_tempo=True)
    sync_cel.sincronizar()   # celular envia (aceito, servidor ainda não tem outra)
    sync_pc.sincronizar()    # PC envia a mais nova e vence
    sync_cel.sincronizar()   # celular recebe
    assert pc.banco.obter_tarefa_por_uuid(t.uuid).titulo == "Editado no PC"
    assert cel.banco.obter_tarefa_por_uuid(t.uuid).titulo == "Editado no PC"


def test_edicao_antiga_enviada_depois_nao_sobrescreve(mundo):
    pc, sync_pc, cel, sync_cel, *_ = mundo
    t = pc.adicionar_rapido("Original")
    sync_pc.sincronizar(); sync_cel.sincronizar()
    # celular fica offline e edita; PC edita depois e sincroniza antes
    c = cel.banco.obter_tarefa_por_uuid(t.uuid)
    c.titulo = "Antiga do celular"
    cel.salvar(c)
    p = pc.banco.obter_tarefa(t.id)
    p.titulo = "Nova do PC"
    pc.salvar(p)
    p.atualizada_em = c.atualizada_em + timedelta(minutes=1)
    pc.banco.salvar_tarefa(p, preservar_tempo=True)
    sync_pc.sincronizar()
    sync_cel.sincronizar()   # envia a antiga (rejeitada) e recebe a nova
    assert cel.banco.obter_tarefa_por_uuid(t.uuid).titulo == "Nova do PC"


def test_tarefa_apagada_e_concluida_se_propagam(mundo):
    pc, sync_pc, cel, sync_cel, *_ = mundo
    a = pc.adicionar_rapido("Vai ser apagada")
    b = pc.adicionar_rapido("Vai ser concluída")
    sync_pc.sincronizar(); sync_cel.sincronizar()
    pc.apagar(a.id)
    pc.alternar_conclusao(b.id)
    sync_pc.sincronizar(); sync_cel.sincronizar()
    assert titulos(cel) == ["Vai ser concluída"]  # a apagada some das listas
    assert cel.banco.obter_tarefa_por_uuid(b.uuid).concluida
    assert cel.banco.obter_tarefa_por_uuid(a.uuid).apagada_em is not None


def test_subtarefas_e_filtros_sincronizam(mundo):
    pc, sync_pc, cel, sync_cel, *_ = mundo
    pai = pc.adicionar_rapido("Viagem")
    pc.adicionar_subtarefa(pai.id, "Passagem")
    pc.criar_filtro("Urgentes", {"prazo": "hoje", "prioridade_min": 2})
    sync_pc.sincronizar(); sync_cel.sincronizar()
    pai_cel = cel.banco.obter_tarefa_por_uuid(pai.uuid)
    assert [s.titulo for s in cel.subtarefas(pai_cel.id)] == ["Passagem"]
    assert [f.nome for f in cel.banco.listar_filtros()] == ["Urgentes"]
    assert cel.banco.listar_filtros()[0].criterios["prioridade_min"] == 2


def test_criacoes_simultaneas_em_dois_aparelhos_se_juntam(mundo):
    pc, sync_pc, cel, sync_cel, *_ = mundo
    pc.adicionar_rapido("Do PC")
    cel.adicionar_rapido("Do celular")
    sync_pc.sincronizar(); sync_cel.sincronizar(); sync_pc.sincronizar()
    assert titulos(pc) == titulos(cel) == ["Do PC", "Do celular"]


def test_lembrete_nao_repete_depois_de_sincronizar(mundo):
    from datetime import datetime
    pc, sync_pc, cel, sync_cel, *_ = mundo
    t = pc.adicionar_rapido("Remédio às 8h")
    sync_pc.sincronizar(); sync_cel.sincronizar()
    agora = datetime.combine(t.prazo, t.prazo_hora) + timedelta(minutes=1)
    avisos = cel.lembretes_vencidos(agora)
    assert len(avisos) == 1  # o celular avisa a tarefa que veio do PC


def test_token_errado_e_recusado(mundo):
    *_, http = mundo
    r = http.post("/sincronizar", json={"dispositivo": "x"}, headers={"Authorization": "Bearer errado"})
    assert r.status_code == 401
    assert http.post("/sincronizar", json={"dispositivo": "x"}).status_code == 401
    assert http.get("/saude").json() == {"ok": True}


def test_token_curto_nao_e_aceito():
    with pytest.raises(ValueError):
        criar_app(Banco(":memory:", varias_threads=True), "123")


def test_servidor_guarda_copia_completa(mundo):
    pc, sync_pc, _cel, _s, servidor, _http = mundo
    pc.adicionar_rapido("Guardada")
    sync_pc.sincronizar()
    assert [t.titulo for t in servidor.consultar()] == ["Guardada"]
