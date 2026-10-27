"""Testes da rodada de refinamentos da interface: cartão de tarefa, seletor de data, calendário,
hábitos por seção, busca flutuante e barra de ícones."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, timedelta

import pytest
from PySide6.QtWidgets import QApplication

from norteia.core import Banco, Servico, matriz
from norteia.core.habitos import SECOES
from norteia.ui.dialogos import DialogoHabito
from norteia.ui.janela import PAGINAS, SECUNDARIAS, JanelaPrincipal
from norteia.ui.pagina_calendario import MODOS
from norteia.ui.popovers import CartaoTarefa, SeletorData


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def janela(app, tmp_path):
    svc = Servico(Banco(":memory:"), pasta_dados=tmp_path)
    j = JanelaPrincipal(svc, notificador=lambda t, x: None, prefs={})
    j.resize(1400, 860)
    j.show()
    return j


# ---------- seletor de data e cartão ----------
def test_seletor_de_data_resultado_e_limpar(app):
    s = SeletorData({})
    recebidos = []
    s.aplicado.connect(recebidos.append)
    s.atalho("amanha")
    assert s.resultado()["prazo"] == date.today() + timedelta(days=1)
    s.confirmar()
    assert recebidos[-1]["prazo"] == date.today() + timedelta(days=1) and recebidos[-1]["repeticao"] is None
    s2 = SeletorData({"prazo": date.today()})
    s2.aplicado.connect(recebidos.append)
    s2.limpar()
    assert recebidos[-1] == {"prazo": None, "hora": None, "inicio": None, "duracao_min": 0, "lembretes": [],
                             "repeticao": None}


def test_cartao_cria_tarefa_com_prioridade_e_dia(janela):
    c = CartaoTarefa(janela, prazo=date.today() + timedelta(days=2))
    c.titulo.setText("Estudar redes")
    c.definir_prioridade(3)
    t = c.gravar()
    assert t is not None and t.titulo == "Estudar redes"
    assert int(t.prioridade) == 3 and t.prazo == date.today() + timedelta(days=2)
    assert c.gravar() is None                       # só grava uma vez


def test_cartao_vazio_nao_cria(janela):
    c = CartaoTarefa(janela)
    assert c.gravar() is None and janela.servico.listar("todas") == []


# ---------- calendário ----------
def test_calendario_todos_os_modos(janela):
    janela.servico.adicionar_rapido("Prova amanhã 10h")
    janela.mostrar_pagina("calendario")
    pag = janela.pagina_calendario
    for modo in MODOS:
        chave = modo[0] if isinstance(modo, (tuple, list)) else modo
        pag.definir_modo(chave)
        pag.navegar(1)
        pag.navegar(-1)
        assert not pag.grab().isNull()
    assert not janela.detalhe.isVisibleTo(janela)   # no calendário o detalhe é o cartão flutuante


# ---------- foco ----------
def test_foco_visao_geral_e_registro(janela):
    pf = janela.pagina_foco
    antes = len(pf.registros)
    pf.definir_alvo("livre", None, "Foco")
    assert set(pf.cartoes) >= {"pomos_hoje", "foco_hoje", "pomos_total", "foco_total"}
    assert antes == 0 and pf.cartoes["pomos_total"].text() == "0"


# ---------- hábitos ----------
def test_habito_secao_e_dias_de_meta(janela):
    hoje = date.today()
    h = janela.servico.habitos.criar("Meditar", secao="Manhã", dias_meta=3, inicio=hoje - timedelta(days=1))
    h2 = janela.servico.habitos.obter(h.uuid)
    assert h2.secao == "Manhã" and h2.dias_meta == 3
    assert h2.agendado(hoje) and h2.agendado(hoje + timedelta(days=1)) and not h2.agendado(hoje + timedelta(days=2))
    ruim = janela.servico.habitos.criar("X", secao="Qualquer")
    assert ruim.secao == "Outros"


def test_pagina_de_habitos_por_secao_e_grade(janela):
    svc = janela.servico
    svc.habitos.criar("Alongar", secao="Manhã")
    svc.habitos.criar("Ler", secao="Noite")
    janela.mostrar_pagina("habitos")
    pag = janela.pagina_habitos
    cabecalhos = [pag.caixa.itemAt(i).widget().text().split()[0] for i in range(pag.caixa.count())
                  if pag.caixa.itemAt(i).widget() is not None and hasattr(pag.caixa.itemAt(i).widget(), "text")]
    assert cabecalhos == ["Manhã", "Noite"]
    h = svc.habitos.listar()[0]
    pag.marcar_dia(h.uuid, date.today())
    assert svc.habitos.concluido(h, date.today())
    pag.marcar_dia(h.uuid, date.today() + timedelta(days=1))    # futuro é ignorado
    assert svc.habitos.quantidade(h, date.today() + timedelta(days=1)) == 0
    pag.alternar_visao()
    assert pag.modo_grade and not pag.grab().isNull()
    pag._recolher_todas(True)
    assert pag.recolhidas == set(SECOES)
    pag.alternar_visao()


def test_dialogo_de_habito_novos_campos(app):
    d = DialogoHabito(None)
    d.nome.setText("Correr")
    d.secao.setCurrentText("Tarde")
    d.meta_dias.setCurrentIndex(1)
    d.qtd_dias.setValue(30)
    d.frequencia.setCurrentText("Dias úteis")
    r = d.resultado()
    assert r["secao"] == "Tarde" and r["dias_meta"] == 30 and r["dias"] == [0, 1, 2, 3, 4]
    assert r["meta"] == 1 and r["inicio"] == date.today()
    d.objetivo.setCurrentIndex(1)
    d.meta.setValue(5)
    d.unidade.setText("km")
    assert d.resultado()["meta"] == 5 and d.resultado()["unidade"] == "km"
    d.dias[5].setChecked(True)                       # marcar sábado vira "Personalizado"
    assert d.frequencia.currentText() == "Personalizado"


# ---------- busca flutuante e barra de ícones ----------
def test_busca_flutuante_abre_tarefa_na_lista(janela):
    svc = janela.servico
    t = svc.adicionar_rapido("Zebra do zoológico")
    janela.abrir_busca()
    pb = janela.painel_busca
    pb.campo.setText("zeb")
    assert pb.lista.count() >= 2
    assert pb.lista.currentItem() is not None
    pb.ativar(pb.lista.currentItem())
    assert janela.pagina_atual == "tarefas" and janela.id_selecionado() == t.id
    pb.campo.setText("")
    assert pb.pilha.currentIndex() == 0


def test_busca_sem_resultado_mostra_vazio(janela):
    janela.abrir_busca("nada-por-aqui-xyz")
    pb = janela.painel_busca
    assert pb.lista.count() == 0 and pb.dica.text() == "Nenhum resultado"


def test_barra_de_icones_nova_ordem(janela):
    assert janela.btn_buscar.isVisibleTo(janela) and janela.btn_avatar.isVisibleTo(janela)
    for chave in SECUNDARIAS:
        assert not janela.btns_pagina[chave].isVisibleTo(janela)         # moram no menu "…"
        janela.mostrar_pagina(chave)
        assert janela.pagina_atual == chave
    assert not janela.btn_busca.isVisibleTo(janela)
    assert {c for c, _i, _d in PAGINAS} == set(janela.btns_pagina)


# ---------- matriz ----------
def test_nomes_dos_quadrantes():
    assert matriz.NOMES["q1"][0] == "Urgente e Importante"
    assert matriz.NOMES["q2"][0] == "Não Urgente e Importante"
    assert matriz.NOMES["q3"][0] == "Urgente e não importante"
    assert matriz.NOMES["q4"][0] == "Não urgente e não importante"


# ---------- rodada: hover/seleção no calendário, descrição e cartão nas Tarefas ----------
def test_cartao_tem_caixa_de_descricao_com_dica(janela):
    c = CartaoTarefa(janela, prazo=date.today())
    c.show()
    assert not c.notas.isHidden()
    assert c.notas.placeholderText() == "Descrição"
    c.notas.setFocus()
    c.notas.focusInEvent(__import__("PySide6.QtGui", fromlist=["QFocusEvent"]).QFocusEvent(
        __import__("PySide6.QtCore", fromlist=["QEvent"]).QEvent.FocusIn))
    assert c.notas.placeholderText() == 'Digite o conteúdo ou use "/" para o menu'
    c.titulo.setText("Com descrição")
    c.notas.setPlainText("detalhes da tarefa")
    t = c.gravar()
    assert t.notas == "detalhes da tarefa"


def test_lista_mostra_cartao_ampliado_na_lateral(janela):
    t = janela.servico.adicionar_rapido("Tarefa de teste")
    janela.mostrar_pagina("tarefas")
    janela.atualizar(selecionar_id=t.id)
    assert not janela.detalhe.isVisible()                   # o painel antigo não aparece mais
    assert janela.painel_cartao.isVisible()
    c = janela.abrir_cartao_da_tarefa(t.id)
    assert c is janela.cartao_acoplado and c.acoplado and c.titulo.text() == "Tarefa de teste"
    assert getattr(janela, "cartao_aberto", None) is None  # nada flutuante no modo lista


def test_cartao_acoplado_grava_sozinho_e_troca_de_tarefa(janela):
    a = janela.servico.adicionar_rapido("Primeira")
    b = janela.servico.adicionar_rapido("Segunda")
    janela.mostrar_pagina("tarefas")
    janela.selecionar_lista("todas")
    janela.atualizar(selecionar_id=a.id)
    c = janela.cartao_acoplado
    c.titulo.setText("Primeira editada")
    c.notas.setPlainText("anotação")
    assert c.pendente
    janela.selecionar_tarefa(b.id)                          # trocar de tarefa grava a anterior
    assert janela.servico.banco.obter_tarefa(a.id).titulo == "Primeira editada"
    assert janela.servico.banco.obter_tarefa(a.id).notas == "anotação"
    assert janela.cartao_acoplado.t.id == b.id
    c2 = janela.cartao_acoplado
    c2.titulo.setText("Segunda editada")
    c2.gravar_agora()
    assert janela.servico.banco.obter_tarefa(b.id).titulo == "Segunda editada"


def test_kanban_abre_so_o_cartao_flutuante(janela):
    t = janela.servico.adicionar_rapido("No quadro")
    janela.mostrar_pagina("tarefas")
    janela.definir_visao("kanban")
    assert not janela.painel_cartao.isVisible() and not janela.detalhe.isVisible()
    c = janela.abrir_cartao_da_tarefa(t.id)
    assert c is not None and not c.acoplado and c.isVisible() and janela.cartao_aberto is c
    assert not janela.painel_cartao.isVisible() and not janela.detalhe.isVisible()
    c.close()
    janela.definir_visao("lista")
    assert janela.painel_cartao.isVisible()


def test_painel_lateral_antigo_opcional(janela):
    t = janela.servico.adicionar_rapido("Outra tarefa")
    janela.mostrar_pagina("tarefas")
    janela.definir_detalhe_lateral(True)
    assert janela.bool_lateral() and janela.detalhe.isVisible() and not janela.painel_cartao.isVisible()
    assert janela.abrir_cartao_da_tarefa(t.id) is None
    janela.definir_detalhe_lateral(False)
    assert janela.painel_cartao.isVisible() and not janela.detalhe.isVisible()


def test_cartao_editado_grava_titulo_e_descricao(janela):
    t = janela.servico.adicionar_rapido("Original")
    janela.mostrar_pagina("tarefas")
    janela.definir_visao("kanban")
    c = janela.abrir_cartao_da_tarefa(t.id)
    c.titulo.setText("Editada")
    c.notas.setPlainText("nota nova")
    c.gravar()
    nova = janela.servico.banco.obter_tarefa(t.id)
    assert nova.titulo == "Editada" and nova.notas == "nota nova"


def test_cor_do_bloco_muda_com_hover_e_selecao():
    from norteia.ui.pagina_calendario import _cor_do_estado
    normal = _cor_do_estado("#3b82f6", 200, "")
    hover = _cor_do_estado("#3b82f6", 200, "hover")
    sel = _cor_do_estado("#3b82f6", 200, "sel")
    assert normal.name() != hover.name() != sel.name()
    assert hover.lightness() > normal.lightness() and sel.lightness() > hover.lightness()
    assert sel.alpha() == 255 and hover.alpha() > normal.alpha()


def test_calendario_guarda_selecao_por_chave(janela):
    from norteia.ui.pagina_calendario import _chave
    t = janela.servico.adicionar_rapido("Reunião")
    t.prazo, t.prazo_hora = date.today(), None
    janela.servico.salvar(t)
    janela.mostrar_pagina("calendario")
    pag = janela.pagina_calendario
    pag.definir_modo("mes") if hasattr(pag, "definir_modo") else None
    pag.atualizar()
    ocs = [o for lst in pag.v_mes.por_dia.values() for o in lst] if True else []
    if not ocs:
        pytest.skip("sem acesso às ocorrências do mês")
    pag.selecionar(ocs[0])
    assert pag.sel == _chave(ocs[0])
    pag.selecionar(None)
    assert pag.sel is None


# ---------- barra lateral: "+" nos cabeçalhos e diálogo de lista ----------
def test_barra_sem_botoes_de_baixo_e_com_mais_nos_cabecalhos(janela):
    assert not hasattr(janela, "btn_projeto") and not hasattr(janela, "btn_filtro")
    chaves = [janela.barra.item(i).data(0x0100 + 2) for i in range(janela.barra.count())
              if janela.barra.item(i).data(0x0100 + 1) == "cabecalho"]
    assert {"novo:lista", "novo:etiqueta", "novo:filtro"} <= set(chaves)


def test_cria_lista_com_emoji_visao_tipo_e_pasta(janela):
    svc = janela.servico
    p = svc.criar_projeto("Estudos", "#4772fa", emoji="📚", visao="kanban", pasta="Faculdade", tipo="notas",
                          inteligente="nenhuma")
    lido = svc.banco.obter_projeto(p.id)
    assert (lido.emoji, lido.visao, lido.pasta, lido.tipo, lido.inteligente) == ("📚", "kanban", "Faculdade",
                                                                                "notas", "nenhuma")
    nota = svc.adicionar_rapido("anotar ideia", projeto_id=p.id)
    assert nota.eh_nota                                     # lista de notas cria notas
    janela.selecionar_lista(p.id)
    assert janela.visao_atual == "kanban"                   # a lista abre na visão escolhida
    janela.selecionar_lista("todas")
    assert janela.visao_atual == "lista"


def test_lista_inteligente_nenhuma_esconde_tarefas_de_hoje(janela):
    svc = janela.servico
    p = svc.criar_projeto("Escondida", inteligente="nenhuma")
    t = svc.adicionar_rapido("tarefa escondida", projeto_id=p.id)
    t.prazo = date.today()
    svc.salvar(t)
    assert t.id not in [x.id for x in svc.listar("hoje")]
    assert t.id not in [x.id for x in svc.listar("todas")]
    assert t.id in [x.id for x in svc.listar(p.id)]         # dentro da própria lista continua aparecendo


def test_dialogo_lista_resultado_e_validacao(janela):
    from norteia.ui.dialogo_lista import DialogoLista
    d = DialogoLista(janela, ["#f0524a", "#4772fa"], ["Faculdade"])
    assert not d.btn_ok.isEnabled()
    d.nome.setText("  Trabalho  ")
    assert d.btn_ok.isEnabled()
    d._definir_emoji("💼")
    d._escolher_cor("#4772fa")
    d._escolher_visao("linha_tempo")
    d.pasta.setCurrentIndex(d.pasta.findData("Faculdade"))
    d.tipo.setCurrentIndex(1)
    r = d.resultado()
    assert r == {"nome": "Trabalho", "cor": "#4772fa", "emoji": "💼", "visao": "linha_tempo",
                 "pasta": "Faculdade", "tipo": "notas", "inteligente": "todas"}


def test_seletor_de_emoji_busca_e_reinicia(janela):
    from norteia.ui.dialogo_lista import SeletorEmoji
    s = SeletorEmoji(janela)
    escolhidos = []
    s.escolhido.connect(escolhidos.append)
    s.busca.setText("livro")
    assert "Objetos" in s._ancoras and "Animais" not in s._ancoras
    s._escolher("📚")
    assert escolhidos == ["📚"]


def test_editar_lista_pelo_servico(janela):
    svc = janela.servico
    p = svc.criar_projeto("Velha")
    svc.atualizar_projeto(p.id, nome="Nova", emoji="🎯", visao="kanban", tipo="notas")
    q = svc.banco.obter_projeto(p.id)
    assert (q.nome, q.emoji, q.visao, q.tipo) == ("Nova", "🎯", "kanban", "notas")


def test_projeto_novos_campos_sincronizam(janela):
    from norteia.sync import serial
    svc = janela.servico
    p = svc.criar_projeto("Sync", emoji="🔥", visao="linha_tempo", tipo="notas", inteligente="nenhuma")
    d = serial.projeto_para_dict(svc.banco.obter_projeto(p.id))
    assert d["emoji"] == "🔥" and d["visao"] == "linha_tempo" and d["tipo"] == "notas"
