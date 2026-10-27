import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from fastapi.testclient import TestClient
from PySide6.QtWidgets import QApplication

from norteia.core import Banco, Servico
from norteia.sync import Sincronizador
from norteia.sync.cliente import ErroSincronizacao
from norteia.sync.servidor import criar_app
from norteia.ui.janela import JanelaPrincipal

TOKEN = "senha-de-teste-123"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def http():
    return TestClient(criar_app(Banco(":memory:", varias_threads=True), TOKEN))


def _janela(http, token=TOKEN):
    svc = Servico(Banco(":memory:"))

    def transporte(caminho, corpo):
        r = http.post(caminho, json=corpo, headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 401:
            raise ErroSincronizacao("Token recusado pelo servidor.")
        return r.json()

    return JanelaPrincipal(svc, sincronizador=Sincronizador(svc.banco, transporte), sync_em_thread=False)


def test_botao_sincronizar_leva_e_traz_tarefas(app, http):
    a, b = _janela(http), _janela(http)
    a.entrada.setText("Vinda do computador")
    a.entrada.returnPressed.emit()
    a.sincronizar_agora()
    assert "Sincronizado" in a.btn_sync.toolTip()
    b.sincronizar_agora()
    b.selecionar_lista("hoje")
    assert b.tarefas.count() == 1
    assert b.tarefas.item(0).data(0x0100).titulo == "Vinda do computador"


def test_falha_de_sincronizacao_avisa_e_nao_quebra(app, http):
    j = _janela(http, token="token-errado-123")
    j.entrada.setText("Local continua funcionando")
    j.entrada.returnPressed.emit()
    j.sincronizar_agora()
    assert "Falha" in j.btn_sync.toolTip() and "Token" in j.btn_sync.toolTip()
    assert j.tarefas.count() == 1 and not j._sincronizando


def test_sem_servidor_configurado_nao_sincroniza(app):
    j = JanelaPrincipal(Servico(Banco(":memory:")))
    assert j.sincronizador is None
    assert "desligada" in j.btn_sync.toolTip()
    j._sync_automatica()  # não deve fazer nada nem levantar erro
