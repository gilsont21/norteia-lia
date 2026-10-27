import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from norteia.core import CAIXA, Banco, Servico, chave_tag
from norteia.ui.delegados import PAPEL_CHAVE, PAPEL_TAREFA
from norteia.ui.janela import JanelaPrincipal


@pytest.fixture
def svc():
    return Servico(Banco(":memory:"))


def test_caixa_tem_so_tarefas_sem_projeto(svc):
    p = svc.criar_projeto("Casa")
    svc.adicionar_rapido("Solta")
    svc.adicionar_rapido("Em lista", projeto_id=p.id)
    assert [t.titulo for t in svc.listar(CAIXA)] == ["Solta"]


def test_lista_de_etiqueta_e_contagem(svc):
    svc.adicionar_rapido("A #casa")
    svc.adicionar_rapido("B #casa #estudo")
    svc.adicionar_rapido("C #estudo")
    assert sorted(t.titulo for t in svc.listar(chave_tag("casa"))) == ["A", "B"]
    c = svc.contagens()
    assert c[chave_tag("casa")] == 2 and c[chave_tag("estudo")] == 2


def test_busca_em_titulo_notas_e_etiqueta(svc):
    a = svc.adicionar_rapido("Pagar boleto")
    b = svc.adicionar_rapido("Outra coisa")
    b.notas = "lembrar do boleto da luz"
    svc.salvar(b)
    svc.adicionar_rapido("Tarefa #boletos")
    svc.adicionar_rapido("Nada a ver")
    assert len(svc.buscar("boleto")) == 3
    assert svc.buscar("   ") == []


def test_busca_ignora_lixeira(svc):
    t = svc.adicionar_rapido("Pagar boleto")
    svc.apagar(t.id)
    assert svc.buscar("boleto") == []


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_ui_busca_e_ordenacao(app):
    j = JanelaPrincipal(Servico(Banco(":memory:")))
    for texto in ("Zebra !1", "Abelha !3", "Macaco"):
        j.servico.adicionar_rapido(texto)
    j.selecionar_lista("caixa")
    j.definir_ordem("titulo")
    assert [j.tarefas.item(i).data(PAPEL_TAREFA).titulo for i in range(3)] == ["Abelha", "Macaco", "Zebra"]
    j.definir_ordem("prioridade")
    assert j.tarefas.item(0).data(PAPEL_TAREFA).titulo == "Abelha"
    j.btn_busca.setChecked(True)
    j.busca.setText("zeb")
    assert j.tarefas.count() == 1 and j.titulo.text() == "Busca"
    j.btn_busca.setChecked(False)
    assert j.tarefas.count() == 3


# ---------- etapa 4 na interface ----------
from norteia.core import chave_filtro


def _janela():
    return JanelaPrincipal(Servico(Banco(":memory:")))


def test_ui_subtarefas_no_detalhe(app):
    j = _janela()
    t = j.servico.adicionar_rapido("Mudança hoje")
    j.atualizar(selecionar_id=t.id)
    j.detalhe.nova_sub.setText("Embalar louça")
    j.detalhe.nova_sub.returnPressed.emit()
    j.detalhe.nova_sub.setText("Chamar caminhão")
    j.detalhe.nova_sub.returnPressed.emit()
    assert [s.titulo for s in j.servico.subtarefas(t.id)] == ["Embalar louça", "Chamar caminhão"]
    assert j.detalhe.subs_caixa.count() == 2
    sub_id = j.servico.subtarefas(t.id)[0].id
    j.detalhe._alternar_sub(sub_id)
    assert j.servico.progresso(t.id) == (1, 2)
    assert j.detalhe.rot_subs.text().endswith("1/2")
    assert j.delegado.progressos[t.id] == (1, 2)
    j.detalhe._apagar_sub(sub_id)
    assert j.servico.progresso(t.id) == (0, 1)


def test_ui_ordem_manual_por_arrastar(app):
    j = _janela()
    for x in ("A", "B", "C"):
        j.servico.adicionar_rapido(x + " hoje")
    j.definir_ordem("manual")
    assert [j.tarefas.item(i).data(PAPEL_TAREFA).titulo for i in range(3)] == ["A", "B", "C"]
    assert j.tarefas.dragDropMode().name == "InternalMove"
    item = j.tarefas.takeItem(2)          # simula soltar o "C" no topo
    j.tarefas.insertItem(0, item)
    j.aplicar_ordem_da_lista()
    assert [j.tarefas.item(i).data(PAPEL_TAREFA).titulo for i in range(3)] == ["C", "A", "B"]
    j.definir_ordem("data")
    assert j.tarefas.dragDropMode().name == "NoDragDrop"


def test_ui_filtro_salvo_aparece_na_barra_e_filtra(app):
    j = _janela()
    j.servico.adicionar_rapido("Importante hoje !3")
    j.servico.adicionar_rapido("Banal hoje")
    f = j.servico.criar_filtro("Só alta", {"prioridade_min": 3})
    j.atualizar()
    chaves = [j.barra.item(i).data(PAPEL_CHAVE) for i in range(j.barra.count())]
    assert chave_filtro(f.id) in chaves
    j.selecionar_lista(chave_filtro(f.id))
    assert j.titulo.text() == "Só alta" and j.tarefas.count() == 1
    j.excluir_filtro(chave_filtro(f.id))
    assert j.lista_atual == "hoje"
