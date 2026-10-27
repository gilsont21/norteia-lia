import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from norteia.core import Banco, Servico
from norteia.ui.delegados import PAPEL_TAREFA
from norteia.ui.janela import JanelaPrincipal


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def janela(app):
    j = JanelaPrincipal(Servico(Banco(":memory:")))
    j.show()
    return j


def test_adicionar_pela_entrada_rapida_vai_para_hoje(janela):
    janela.entrada.setText("Estudar #si601 !2")
    janela.entrada.returnPressed.emit()
    assert janela.tarefas.count() == 1
    t = janela.tarefas.item(0).data(PAPEL_TAREFA)
    assert t.titulo == "Estudar" and t.tags == ["si601"] and t.prazo is not None


def test_concluir_remove_da_lista(janela):
    janela.entrada.setText("Qualquer coisa")
    janela.entrada.returnPressed.emit()
    janela.alternar(janela.tarefas.item(0).data(PAPEL_TAREFA).id)
    assert janela.tarefas.count() == 0


def test_editar_titulo_no_detalhe_salva(janela):
    janela.entrada.setText("Antigo")
    janela.entrada.returnPressed.emit()
    janela.tarefas.setCurrentRow(0)
    janela.detalhe.titulo.setText("Novo título")
    janela.detalhe.titulo.editingFinished.emit()
    assert janela.servico.banco.consultar()[0].titulo == "Novo título"


# ---------- etapa 3: hora, repetição, lembretes ----------
from datetime import date, datetime, time

from PySide6.QtWidgets import QApplication as _QA  # noqa: F401


def _selecionar_nova(janela, texto):
    janela.entrada.setText(texto)
    janela.entrada.returnPressed.emit()
    janela.tarefas.setCurrentRow(0)


def test_detalhe_mostra_hora_repeticao_e_lembrete(janela):
    _selecionar_nova(janela, "Academia todo dia às 7h")
    d = janela.detalhe
    assert d.tem_hora.isChecked() and d.hora.time().hour() == 7
    assert d.repetir.currentData() == "FREQ=DAILY"
    assert d.lembrar.currentData() == [0]


def test_editar_repeticao_hora_e_lembrete_salva(janela):
    _selecionar_nova(janela, "Relatório")
    d = janela.detalhe
    d.tem_prazo.setChecked(True)
    d.tem_hora.setChecked(True)
    d.hora.setTime(d.hora.time().fromString("16:45", "HH:mm"))
    d.repetir.setCurrentIndex(d.repetir.findData("FREQ=WEEKLY"))
    d.lembrar.setCurrentIndex(d.lembrar.findData([30]))
    t = janela.servico.banco.consultar()[0]
    assert t.prazo_hora == time(16, 45)
    assert t.repeticao == "FREQ=WEEKLY" and t.lembretes == [30]


def test_regra_personalizada_e_preservada(janela):
    _selecionar_nova(janela, "Quinzenal")
    t = janela.servico.banco.consultar()[0]
    t.repeticao, t.lembretes = "FREQ=WEEKLY;INTERVAL=2", [10, 60]
    janela.servico.salvar(t)
    janela.atualizar(selecionar_id=t.id)
    janela.detalhe.titulo.editingFinished.emit()  # qualquer salvamento
    salvo = janela.servico.banco.consultar()[0]
    assert salvo.repeticao == "FREQ=WEEKLY;INTERVAL=2" and salvo.lembretes == [10, 60]


def test_verificar_lembretes_avisa_uma_vez(app):
    avisos = []
    j = JanelaPrincipal(Servico(Banco(":memory:")), notificador=lambda a, b: avisos.append((a, b)))
    t = j.servico.adicionar_rapido("Remédio às 8h")
    agora = datetime.combine(t.prazo, time(8, 1))
    assert len(j.verificar_lembretes(agora)) == 1
    assert avisos == [("Remédio", "Vence agora")]
    assert j.verificar_lembretes(agora) == []
    assert len(avisos) == 1
