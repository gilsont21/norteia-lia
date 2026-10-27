"""Telas do Google Calendar: grade de integrações, login, calendários marcáveis e sincronização."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication

from norteia.core import Banco, Servico
from norteia.core.google_agenda import Cofre, Google
from norteia.ui.dialogo_google import DialogoGoogle, DialogoIntegracoes, GerenteGoogle
from norteia.ui.janela import JanelaPrincipal
from tests.test_google_agenda import GoogleFalso


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def mundo(app, tmp_path):
    svc = Servico(Banco(":memory:"), pasta_dados=tmp_path)
    falso = GoogleFalso()
    svc._extras["google"] = Google(svc, transporte=falso, cofre=Cofre(svc.banco, usar_keyring=False))
    return svc, falso


def test_grade_so_google_e_url_estao_ativos(mundo, app):
    chamadas = []
    d = DialogoIntegracoes(None, lambda: chamadas.append("g"), lambda: chamadas.append("u"))
    ativos = [c for c in d.cartoes if c.ativo]
    assert len(ativos) == 2 and len(d.cartoes) > 6
    d.cartoes[2].mousePressEvent = lambda e: None   # (os "em breve" não são clicáveis)
    assert not d.cartoes[2].ativo
    ativos[0].clicado.emit()
    assert chamadas == ["g"]


def test_sem_credenciais_pede_para_preencher(mundo, app):
    svc, _ = mundo
    g = GerenteGoogle(svc, em_thread=False)
    d = DialogoGoogle(None, svc, g)
    assert d.paginas.currentIndex() == 0
    d.conectar()
    assert "Preencha" in d.status.text()
    assert not svc.google.conectado


def test_login_conecta_e_lista_calendarios_desmarcados(mundo, app, monkeypatch):
    svc, falso = mundo
    abertos = []
    g = GerenteGoogle(svc, em_thread=False, transporte=falso, abrir=abertos.append)
    # o login de verdade abre o navegador e espera o retorno; aqui simulamos o resultado dele
    import norteia.ui.dialogo_google as dg
    monkeypatch.setattr(dg.ga, "login_pelo_navegador",
                        lambda *a, **k: {"refresh_token": "r1", "access_token": "a1", "expira_em": 9e12})
    d = DialogoGoogle(None, svc, g)
    d.campo_id.setText("meu-id")
    d.campo_segredo.setText("meu-segredo")
    d.conectar()
    assert svc.google.conectado and d.paginas.currentIndex() == 1
    assert {n: c.isChecked() for n, c in d.caixas.items()} == {"Gilson": False, "Trabalho": False}


def test_marcar_calendario_traz_os_eventos(mundo, app):
    svc, falso = mundo
    svc.google.cliente.definir_credenciais("i", "s")
    svc.google.cliente.guardar_login({"refresh_token": "r", "access_token": "", "expira_em": 0})
    falso.por_google("trab@group.calendar.google.com", {"summary": "Reunião", "start": {"dateTime": f"{date.today()}T10:00:00-03:00"},
                                                      "end": {"dateTime": f"{date.today()}T11:00:00-03:00"}})
    g = GerenteGoogle(svc, em_thread=False, transporte=falso)
    g.sincronizar()
    d = DialogoGoogle(None, svc, g)
    d.caixas["Trabalho"].setChecked(True)
    ass = next(a for a in svc.google.calendarios() if a["nome"] == "Trabalho")
    assert ass["ativa"]
    ocs = [o for o in svc.calendario.ocorrencias(date.today(), date.today()) if getattr(o, "externo", False)]
    assert [o.titulo for o in ocs] == ["Reunião"] and ocs[0].link.startswith("https://calendar.google.com")


def test_enviar_tarefas_e_desconectar(mundo, app):
    svc, falso = mundo
    svc.google.cliente.definir_credenciais("i", "s")
    svc.google.cliente.guardar_login({"refresh_token": "r", "access_token": "", "expira_em": 0})
    t = svc.adicionar_rapido("Estudar")
    t.prazo = date.today()
    svc.salvar(t)
    g = GerenteGoogle(svc, em_thread=False, transporte=falso)
    d = DialogoGoogle(None, svc, g)
    g.sincronizar()
    d._atualizar()
    d.chk_enviar.setChecked(True)
    cid, evs = falso.da_tarefa()
    assert [e["summary"] for e in evs.values()] == ["Estudar"]
    d.desconectar()
    assert not svc.google.conectado and d.paginas.currentIndex() == 0


def test_erro_de_autorizacao_aparece_na_tela(mundo, app):
    svc, falso = mundo
    svc.google.cliente.definir_credenciais("i", "s")
    svc.google.cliente.guardar_login({"refresh_token": "r", "access_token": "", "expira_em": 0})
    falso.recusar_refresh = True
    g = GerenteGoogle(svc, em_thread=False, transporte=falso)
    d = DialogoGoogle(None, svc, g)
    g.sincronizar()
    assert d.status.text() and "Pronto" not in d.status.text()


def test_janela_tem_integracoes_no_menu_e_sincroniza_sem_conta(mundo, app):
    svc, _ = mundo
    j = JanelaPrincipal(svc, notificador=lambda t, x: None, prefs={}, google_em_thread=False)
    j.gerente_google.sincronizar()          # sem conta conectada: não faz nada e não quebra
    assert not j.gerente_google.sincronizando
    assert callable(j.abrir_integracoes) and callable(j.abrir_google)
