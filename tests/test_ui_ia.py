"""Telas da IA: configuração (chave que não volta a aparecer), chat, plano com Aplicar e Desfazer."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from datetime import date

import pytest
from PySide6.QtWidgets import QApplication

from norteia.core import Banco, Servico
from norteia.core.ia_provedores import ConfigIA, CofreIA
from norteia.core.models import Tarefa
from norteia.ui.janela import JanelaPrincipal
from norteia.ui.pagina_ia import CartaoPlano, DialogoIA
from tests.test_ia_assistente import Chamada, IAFalsa


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def janela(app, tmp_path):
    svc = Servico(Banco(":memory:"), pasta_dados=tmp_path)
    svc._extras["ia"] = ConfigIA(svc.banco, CofreIA(svc.banco, usar_keyring=False))
    j = JanelaPrincipal(svc, notificador=lambda t, x: None, prefs={}, google_em_thread=False)
    j.resize(1200, 800)
    j.show()
    j.pagina_ia.em_thread = False
    return j


def test_pagina_sem_chave_pede_configuracao(janela):
    p = janela.pagina_ia
    janela.mostrar_pagina("ia")
    assert janela.pagina_atual == "ia" and p.pilha.currentIndex() == 0
    assert "Gemini" in p.titulo.text()


def test_configuracao_chave_some_da_tela_e_so_mostra_o_final(janela):
    svc = janela.servico
    d = DialogoIA(None, svc, em_thread=False)
    assert d.provedor == "gemini" and not d.btn_apagar.isEnabled()
    d.campo_chave.setText("AIza-uma-chave-bem-secreta-9Z9Z")
    d.salvar_chave()
    assert d.campo_chave.text() == ""                                   # campo limpo
    assert d.estado_chave.text().endswith("9Z9Z") and "secreta" not in d.estado_chave.text()
    assert d.btn_apagar.isEnabled()
    d.combo.setCurrentIndex(d.combo.findData("claude"))                 # cada provedor tem a sua chave
    assert d.estado_chave.text() == "sem chave" and svc.ia.ativo == "claude"
    d.campo_chave.setText("curta")
    d.salvar_chave()
    assert "curta demais" in d.status.text()
    d.combo.setCurrentIndex(d.combo.findData("gemini"))
    d.apagar_chave()
    assert d.estado_chave.text() == "sem chave"


def test_testar_conexao_mostra_resultado_ou_erro(janela):
    svc = janela.servico
    svc.ia.salvar_chave("gemini", "chave-de-teste-123")
    d = DialogoIA(None, svc, transporte=IAFalsa("gemini", [("ok", [])]), em_thread=False)
    d.testar()
    assert "Funcionou" in d.status.text() and "ok" in d.status.text()

    def recusa(*a, **k):
        from norteia.core.ia import ErroIA
        raise ErroIA("A chave foi recusada.")

    d.transporte = recusa
    d.testar()
    assert "recusada" in d.status.text()


def test_modelo_avancado_privacidade_e_preferencias_ficam_salvos(janela):
    svc = janela.servico
    d = DialogoIA(None, svc, em_thread=False)
    d.campo_modelo.setText("gemini-meu-modelo")
    d.campo_modelo.editingFinished.emit()
    d.chk_notas.setChecked(False)
    d.campo_pref.setPlainText("não marcar antes das 8h\n\nsábado é folga")
    d.accept()
    assert svc.ia.modelo("gemini") == "gemini-meu-modelo" and not svc.ia.enviar_notas
    assert svc.ia.preferencias == ["não marcar antes das 8h", "sábado é folga"]


def conversar_com(janela, roteiro, texto):
    svc = janela.servico
    svc.ia.salvar_chave("claude", "sk-ant-chave-de-teste")
    svc.ia.definir_ativo("claude")
    p = janela.pagina_ia
    p.transporte = IAFalsa("claude", roteiro)
    janela.mostrar_pagina("ia")
    p.atualizar_estado()
    p.enviar(texto)
    return p


def test_chat_mostra_resposta_propoe_plano_aplica_e_desfaz(janela):
    svc = janela.servico
    t = svc.salvar(Tarefa(titulo="Relatório", prazo=date.today(), ordem=1))
    amanha = date.fromordinal(date.today().toordinal() + 1).isoformat()
    roteiro = [("", [Chamada("c1", "atualizar_tarefa", {"id": t.id, "data": amanha})]),
               ("Adiei o relatório para amanhã. Confira o plano.", [])]
    p = conversar_com(janela, roteiro, "Adie o relatório")
    assert p.pilha.currentIndex() == 1 and not p.ocupado
    textos = [w.text() for w in p.corpo.findChildren(type(p.titulo)) if w.objectName().startswith("bolha_")]
    assert textos == ["Adie o relatório", "Adiei o relatório para amanhã. Confira o plano."]
    assert len(p.cartoes) == 1 and "Relatório" in p.cartoes[0].plano.acoes[0].resumo
    assert svc.banco.obter_tarefa(t.id).prazo == date.today()               # nada mudou ainda
    c: CartaoPlano = p.cartoes[0]
    c.btn_aplicar.click()
    assert svc.banco.obter_tarefa(t.id).prazo.isoformat() == amanha and c.btn_desfazer.isVisibleTo(c)
    c.btn_desfazer.click()
    assert svc.banco.obter_tarefa(t.id).prazo == date.today() and "Desfeito" in c.resultado.text()


def test_descartar_plano_nao_muda_nada(janela):
    svc = janela.servico
    roteiro = [("", [Chamada("c1", "criar_tarefa", {"titulo": "Nova coisa"})]), ("Proposta pronta.", [])]
    p = conversar_com(janela, roteiro, "crie uma tarefa")
    p.cartoes[0].btn_descartar.click()
    assert svc.buscar("Nova coisa") == [] and "Descartado" in p.cartoes[0].resultado.text()


def test_erro_da_ia_aparece_no_chat_sem_travar(janela):
    from norteia.core.ia import ErroIA
    svc = janela.servico
    svc.ia.salvar_chave("claude", "sk-ant-chave-de-teste")
    svc.ia.definir_ativo("claude")
    p = janela.pagina_ia

    def falha(*a, **k):
        raise ErroIA("Limite de uso da IA atingido.")

    p.transporte = falha
    p.atualizar_estado()
    p.enviar("oi")
    assert not p.ocupado and p.btn_enviar.isEnabled()
    assert any("Limite" in w.text() for w in p.corpo.findChildren(type(p.titulo)))


def test_historico_guarda_e_reabre_conversas(janela):
    p = conversar_com(janela, [("Oi! Em que posso ajudar?", [])], "olá")
    cid = p.conversa_id
    assert janela.servico.conversas_ia.listar()[0]["titulo"] == "olá"
    p.nova_conversa()
    assert p.historico == [] and p.sugestoes.isVisibleTo(p)
    p.abrir_conversa(cid)
    assert [m["papel"] for m in p.historico] == ["usuario", "assistente"]
    assert len([w for w in p.corpo.findChildren(type(p.titulo)) if w.objectName().startswith("bolha_")]) == 2


def test_sugestao_rapida_envia_o_pedido(janela):
    p = conversar_com(janela, [("Vamos planejar.", [])], "x")
    p.nova_conversa()
    p.transporte = IAFalsa("claude", [("Plano feito.", [])])
    p.chips[0].click()
    assert "Planeje o meu dia" in p.historico[0]["texto"]


def test_subtarefas_usam_a_ia_escolhida(janela):
    svc = janela.servico
    svc.ia.salvar_chave("deepseek", "chave-deepseek-123")
    svc.ia.definir_ativo("deepseek")
    t = svc.salvar(Tarefa(titulo="Preparar audiência", ordem=1))
    janela.selecionar_tarefa(t.id)
    import norteia.ui.janela as jm
    chamados = []
    original = jm.ia_provedores.quebrar_tarefa
    jm.ia_provedores.quebrar_tarefa = lambda pedido, titulo, notas: (chamados.append(pedido.provedor) or ["A", "B"])
    try:
        janela._ia_em_thread = False
        janela.sugerir_subtarefas(t.id)
    finally:
        jm.ia_provedores.quebrar_tarefa = original
    assert chamados == ["deepseek"] and [s.titulo for s in svc.subtarefas(t.id)] == ["A", "B"]
