"""Testes das telas novas: calendário, quadros, foco, hábitos, contagem, estatísticas e painel de detalhe."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, datetime, time, timedelta

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QDialog

from norteia.core import AMANHA, CAIXA, HOJE, TODAS, Banco, Servico, kanban
from norteia.core.calendario import Ocorrencia
from norteia.ui import janela as janela_mod
from norteia.ui.cartoes import MIME_TAREFA
from norteia.ui.delegados import PAPEL_TAREFA, PAPEL_TIPO
from norteia.ui.janela import PAGINAS, PERSONALIZAR, JanelaPrincipal


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def avisos():
    return []


@pytest.fixture
def janela(app, avisos, tmp_path):
    svc = Servico(Banco(":memory:"), pasta_dados=tmp_path)
    j = JanelaPrincipal(svc, notificador=lambda t, x: avisos.append((t, x)), prefs={})
    j.resize(1400, 860)
    j.show()
    return j


def soltar(lista, tarefa_id: int):
    mime = QMimeData()
    mime.setData(MIME_TAREFA, str(tarefa_id).encode())
    ev = QDropEvent(QPointF(5, 5), Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
    lista.dropEvent(ev)


def nomes_da_barra(j):
    return [(j.barra.item(i).data(PAPEL_TIPO), j.barra.item(i).text()) for i in range(j.barra.count())]


# ---------- coluna de ícones e páginas ----------
def test_todos_os_botoes_do_trilho_estao_ativos(janela):
    assert set(janela.btns_pagina) == {c for c, _i, _d in PAGINAS}
    assert all(b.isEnabled() and b.isCheckable() for b in janela.btns_pagina.values())
    assert janela.btn_tarefas.isChecked()


@pytest.mark.parametrize("chave", [c for c, _i, _d in PAGINAS])
def test_cada_pagina_abre_e_desenha(janela, chave):
    svc = janela.servico
    t = svc.adicionar_rapido("Estudar amanhã às 9h !3")
    svc.salvar(t)
    janela.btns_pagina[chave].click()
    assert janela.pagina_atual == chave
    assert janela.pilha_paginas.currentWidget() is janela.paginas[chave]
    assert janela.btns_pagina[chave].isChecked()
    assert janela.barra_caixa.isVisibleTo(janela) == (chave == "tarefas")
    assert not janela.detalhe.isVisibleTo(janela)        # editar abre o cartão flutuante, não o painel lateral
    assert not janela.paginas[chave].grab().isNull()


def test_ctrl_numero_troca_de_pagina(janela):
    from PySide6.QtGui import QKeySequence, QShortcut

    def atalho(texto):
        return [s for s in janela.findChildren(QShortcut) if s.key() == QKeySequence(texto)][0]

    atalho("Ctrl+2").activated.emit()
    assert janela.pagina_atual == "calendario"
    atalho("Ctrl+7").activated.emit()
    assert janela.pagina_atual == "estatisticas"
    atalho("Ctrl+1").activated.emit()
    assert janela.pagina_atual == "tarefas"


def test_busca_volta_para_a_lista(janela):
    janela.mostrar_pagina("matriz")
    janela.btn_busca.setChecked(True)
    assert janela.pagina_atual == "tarefas"


def test_barra_lateral_volta_ao_estado_escolhido(janela):
    janela.alternar_barra()
    assert not janela.barra_caixa.isVisibleTo(janela)
    janela.mostrar_pagina("calendario")
    janela.mostrar_pagina("tarefas")
    assert not janela.barra_caixa.isVisibleTo(janela)
    janela.alternar_barra()
    assert janela.barra_caixa.isVisibleTo(janela)


# ---------- calendário ----------
def test_calendario_mostra_e_arrasta(janela):
    svc = janela.servico
    t = svc.adicionar_rapido("Reunião")
    t.prazo, t.prazo_hora = date.today(), time(10, 0)
    svc.salvar(t)
    janela.mostrar_pagina("calendario")
    pag = janela.pagina_calendario
    for modo in ("dia", "semana", "mes", "agenda"):
        pag.definir_modo(modo)
        assert not pag.grab().isNull()
    pag.definir_modo("semana")
    ini, fim = pag.periodo()
    assert ini <= date.today() <= fim
    amanha = date.today() + timedelta(days=1)
    pag.mover(t.id, amanha, time(14, 30))
    salvo = svc.banco.obter_tarefa(t.id)
    assert (salvo.prazo, salvo.prazo_hora) == (amanha, time(14, 30))
    pag.redimensionar(t.id, 120)
    assert svc.banco.obter_tarefa(t.id).duracao_min == 120


def test_calendario_criar_tarefa_em_dia_e_hora(janela):
    janela.mostrar_pagina("calendario")
    dia = date.today() + timedelta(days=2)
    janela.pagina_calendario.criar_em("Dentista", dia, time(8, 0))
    t = [x for x in janela.servico.listar(TODAS) if x.titulo == "Dentista"][0]
    assert (t.prazo, t.prazo_hora, t.lembretes) == (dia, time(8, 0), [0])
    assert janela.id_selecionado() == t.id
    assert janela.detalhe.tarefa.id == t.id        # o detalhe aparece mesmo fora da lista


def test_calendario_navegacao_e_semana_na_segunda(janela):
    pag = janela.pagina_calendario
    janela.mostrar_pagina("calendario")
    pag.definir_modo("mes")
    mes = pag.ancora.month
    pag.navegar(+1)
    assert pag.ancora.month == mes % 12 + 1
    pag.ir_hoje()
    assert pag.ancora == date.today()
    janela.prefs["semana_comeca_segunda"] = True
    pag.definir_modo("semana")
    assert pag.periodo()[0].weekday() == 0
    janela.prefs["semana_comeca_segunda"] = False
    assert pag.periodo()[0].weekday() == 6


def test_evento_externo_vira_tarefa(janela):
    o = Ocorrencia("Aula de SAD", date.today(), date.today(), time(19, 0), 90, "#4dd0b1", externo=True)
    menu = janela.menu_da_tarefa_id(None, QPoint(0, 0), externo=o, executar=False)
    textos = [a.text() for a in menu.actions()]
    assert any("somente leitura" in x for x in textos)
    [a for a in menu.actions() if a.text().startswith("Criar tarefa")][0].trigger()
    t = [x for x in janela.servico.listar(TODAS) if x.titulo == "Aula de SAD"][0]
    assert (t.prazo, t.prazo_hora, t.duracao_min) == (date.today(), time(19, 0), 90)


# ---------- Kanban e linha do tempo ----------
def test_kanban_por_secoes_arrastar_e_soltar(janela):
    svc = janela.servico
    p = svc.criar_projeto("Faculdade")
    a = svc.adicionar_rapido("Resumo", projeto_id=p.id)
    kanban.criar_secao(svc, p.id, "Fazendo")
    janela.selecionar_lista(p.id)
    janela.definir_visao("kanban")
    assert janela.kanban.isVisibleTo(janela) and not janela.tarefas.isVisibleTo(janela)
    titulos = [c.coluna.titulo for c in janela.kanban.colunas_w]
    assert titulos == ["Sem seção", "Fazendo"]
    destino = janela.kanban.colunas_w[1]
    soltar(destino.lista, a.id)
    assert svc.banco.obter_tarefa(a.id).secao == "Fazendo"
    assert [c.coluna.titulo for c in janela.kanban.colunas_w][1] == "Fazendo"
    assert janela.kanban.colunas_w[1].lista.count() == 1


def test_kanban_por_prioridade_e_nova_tarefa(janela):
    svc = janela.servico
    t = svc.adicionar_rapido("Algo")
    t.prazo = date.today()
    svc.salvar(t)
    janela.definir_visao("kanban")
    janela.kanban.combo.setCurrentIndex(janela.kanban.combo.findData("prioridade"))
    col_alta = [c for c in janela.kanban.colunas_w if c.coluna.chave == 3][0]
    soltar(col_alta.lista, t.id)
    assert int(svc.banco.obter_tarefa(t.id).prioridade) == 3
    col_alta = [c for c in janela.kanban.colunas_w if c.coluna.chave == 3][0]
    col_alta.entrada.setText("Nova no Kanban")
    col_alta.entrada.returnPressed.emit()
    nova = [x for x in svc.listar(TODAS) if x.titulo == "Nova no Kanban"][0]
    assert int(nova.prioridade) == 3


def test_kanban_secoes_renomear_mover_apagar(janela):
    svc = janela.servico
    p = svc.criar_projeto("X")
    janela.selecionar_lista(p.id)
    janela.definir_visao("kanban")
    kanban.criar_secao(svc, p.id, "A")
    kanban.criar_secao(svc, p.id, "B")
    janela.atualizar()
    janela.kanban.renomear_secao("A", "Alfa")
    janela.kanban.mover_secao("B", -1)
    assert svc.banco.secoes_da_lista(p.id) == ["B", "Alfa"]
    janela.kanban.apagar_secao("B")
    assert svc.banco.secoes_da_lista(p.id) == ["Alfa"]


def test_linha_do_tempo_mover_e_esticar(janela):
    svc = janela.servico
    t = svc.adicionar_rapido("Projeto longo")
    t.prazo = date.today() + timedelta(days=3)
    svc.salvar(t)
    janela.definir_visao("linha_tempo")
    assert janela.linha_tempo.isVisibleTo(janela)
    assert not janela.linha_tempo.grab().isNull()
    v = janela.linha_tempo
    v.aplicar("mover", t, 2)
    assert svc.banco.obter_tarefa(t.id).prazo == date.today() + timedelta(days=5)
    v.aplicar("ini", svc.banco.obter_tarefa(t.id), -2)
    salvo = svc.banco.obter_tarefa(t.id)
    assert salvo.inicio == date.today() + timedelta(days=3) and salvo.prazo == date.today() + timedelta(days=5)
    v.aplicar("fim", salvo, 1)
    assert svc.banco.obter_tarefa(t.id).prazo == date.today() + timedelta(days=6)
    sem = svc.adicionar_rapido("Sem data")
    v.definir_dia(sem, date.today() + timedelta(days=4))
    assert svc.banco.obter_tarefa(sem.id).prazo == date.today() + timedelta(days=4)


def test_voltar_para_lista(janela):
    janela.definir_visao("kanban")
    janela.definir_visao("lista")
    assert janela.tarefas.isVisibleTo(janela) or janela.vazio.isVisibleTo(janela)
    assert not janela.kanban.isVisibleTo(janela)


# ---------- matriz ----------
def test_matriz_arrastar_muda_prioridade_e_prazo(janela):
    svc = janela.servico
    t = svc.adicionar_rapido("Planejar")
    janela.mostrar_pagina("matriz")
    q = janela.pagina_matriz.quadrantes
    total = sum(x.lista.count() for x in q.values())
    assert total == 1
    soltar(q["q1"].lista, t.id)
    salvo = svc.banco.obter_tarefa(t.id)
    assert int(salvo.prioridade) >= 2 and salvo.prazo is not None
    assert q["q1"].lista.count() == 1
    q["q2"].entrada.setText("Estratégia")
    q["q2"].entrada.returnPressed.emit()
    assert q["q2"].lista.count() == 1


# ---------- foco ----------
def test_foco_pomodoro_completo_registra_sessao(janela, avisos):
    svc = janela.servico
    t = svc.adicionar_rapido("Estudar")
    pf = janela.paginas["foco"]
    janela.mostrar_pagina("foco")
    agora = datetime.now().replace(microsecond=0)
    pf._agora = lambda: agora
    pf.escolher_tarefa(t.id)
    pf.iniciar()
    assert pf.cron.ativo and "·" in janela.windowTitle()
    assert not pf.btn_iniciar.isEnabled() and pf.btn_pausar.isEnabled()
    pf.tique(agora + timedelta(minutes=10))
    assert pf.anel.texto == "15:00"
    pf.tique(agora + timedelta(minutes=25))
    assert pf.cron.fase == "pausa_curta"
    assert [a[0] for a in avisos] == ["Foco concluído"]
    sessoes = svc.foco.sessoes(date.today(), date.today())
    assert len(sessoes) == 1 and sessoes[0].duracao_s == 1500 and sessoes[0].tarefa_uuid == t.uuid
    assert len(pf.registros) == 1
    pf.pular()
    assert not pf.cron.ativo and janela.windowTitle() == "Norteia"


def test_foco_pausar_parar_e_cronometro(janela):
    pf = janela.paginas["foco"]
    janela.mostrar_pagina("foco")
    base = datetime.now().replace(microsecond=0)
    relogio = [base]
    pf._agora = lambda: relogio[0]
    pf.definir_modo("cronometro")
    pf.iniciar()
    relogio[0] = base + timedelta(minutes=5)
    pf.alternar_pausa()
    assert pf.cron.pausado and pf.btn_iniciar.text() == "Retomar"
    relogio[0] = base + timedelta(minutes=30)
    pf.iniciar()                                    # retoma
    relogio[0] = base + timedelta(minutes=33)
    pf.parar()
    s = janela.servico.foco.sessoes(date.today(), date.today())
    assert len(s) == 1 and s[0].modo == "cronometro" and s[0].duracao_s == 8 * 60 and not s[0].completa
    assert not pf.cron.ativo


def test_foco_sessao_curta_nao_e_guardada_e_ajustes_vao_para_prefs(janela):
    pf = janela.paginas["foco"]
    agora = datetime.now().replace(microsecond=0)
    pf._agora = lambda: agora
    pf.iniciar()
    pf.parar()
    assert janela.servico.foco.sessoes() == []
    pf.s_foco.setValue(50)
    assert janela.prefs["foco_min"] == 50 and pf.cron.config.foco_min == 50
    assert pf.anel.texto == "50:00"


def test_foco_pelo_botao_da_tarefa_e_ao_fechar(janela):
    svc = janela.servico
    t = svc.adicionar_rapido("Escrever")
    janela.iniciar_foco_na_tarefa(t.id)
    pf = janela.pagina_foco
    assert janela.pagina_atual == "foco" and pf.cron.ativo and pf.combo_tarefa.currentData() == t.id
    base = datetime.now().replace(microsecond=0)
    pf._agora = lambda: base + timedelta(minutes=3)
    pf.cron._inicio = pf.cron._retomado = base
    pf.encerrar()
    assert not pf.cron.ativo
    assert svc.foco.segundos_da_tarefa(t.uuid) == 180


# ---------- hábitos ----------
def test_habitos_criar_marcar_editar_apagar(janela):
    janela.mostrar_pagina("habitos")
    pag = janela.pagina_habitos
    assert pag.vazio.isVisibleTo(pag)
    pag.novo({"nome": "Beber água", "cor": "#4dd0b1", "meta": 3, "unidade": "copos", "dias": list(range(7)),
              "lembrete": None})
    assert pag.detalhe.isVisibleTo(pag) and pag.caixa.count() >= 1
    h = pag.habitos.obter(pag.selecionado)
    pag.marcar_hoje(h.uuid)
    assert pag.habitos.quantidade(h, date.today()) == 1
    pag.marcar_hoje(h.uuid)
    pag.marcar_hoje(h.uuid)
    assert pag.habitos.concluido(h, date.today())
    assert pag.n_atual.text() == "1" and pag.rot_hoje.text() == "Hoje: 1 de 1 feitos"
    pag._clicou_dia(date.today() - timedelta(days=1))
    assert pag.habitos.concluido(h, date.today() - timedelta(days=1))
    assert pag.n_atual.text() == "2"
    pag._clicou_dia(date.today() + timedelta(days=1))          # futuro: ignorado
    assert pag.habitos.quantidade(h, date.today() + timedelta(days=1)) == 0
    pag.editar({"nome": "Água", "cor": "#f5a623", "meta": 3, "unidade": "copos", "dias": [0, 1, 2, 3, 4],
                "lembrete": "18:00"})
    assert pag.det_titulo.text() == "Água" and "18:00" in pag.det_sub.text()
    pag._navegar(-1)
    assert not pag.grade.grab().isNull()
    pag.arquivar()
    assert pag.habitos.obter(h.uuid).arquivado and pag.selecionado is None
    pag.chk_arquivados.setChecked(True)
    assert pag.selecionado == h.uuid
    pag.apagar(confirmar=False)
    assert pag.habitos.listar(arquivados=None) == [] and pag.vazio.isVisibleTo(pag)


def test_habito_lembrete_dispara_uma_vez(janela, avisos):
    h = janela.servico.habitos.criar("Alongar", lembrete="08:00")
    agora = datetime.combine(date.today(), time(9, 0))
    janela.verificar_lembretes(agora)
    janela.verificar_lembretes(agora)
    assert [a for a in avisos if a[0] == "Hábito: Alongar"] and len([a for a in avisos if "Alongar" in a[0]]) == 1
    janela.servico.habitos.alternar(h, date.today())
    assert janela.servico.habitos.pendentes_hoje() == []


# ---------- contagem e estatísticas ----------
def test_contagem_regressiva_na_tela(janela):
    janela.mostrar_pagina("contagem")
    pag = janela.pagina_contagem
    assert pag.vazio.isVisibleTo(pag)
    pag.nova({"nome": "Prova", "data": date.today() + timedelta(days=10), "cor": "#f5a623", "anual": False})
    pag.nova({"nome": "Aniversário", "data": date(2000, 3, 4), "cor": "#4772fa", "anual": True})
    assert not pag.vazio.isVisibleTo(pag) and pag.caixa.count() == 3       # 2 cartões + espaço
    c = [x for x in pag.contagens.listar() if x.nome == "Prova"][0]
    pag.editar(c, {"nome": "Prova final", "data": date.today() + timedelta(days=2), "cor": "#f0524a",
                   "anual": False})
    assert pag.contagens.listar()[0].nome == "Prova final"
    assert not pag.grab().isNull()
    pag.apagar(pag.contagens.listar()[0], confirmar=False)
    assert [x.nome for x in pag.contagens.listar()] == ["Aniversário"]


def test_estatisticas_na_tela(janela):
    svc = janela.servico
    a = svc.adicionar_rapido("Feita")
    svc.alternar_conclusao(a.id)
    svc.adicionar_rapido("Pendente hoje")
    from norteia.core.foco import Sessao
    svc.foco.registrar(Sessao(datetime.now().replace(microsecond=0), 1800))
    h = svc.habitos.criar("Ler")
    svc.habitos.alternar(h, date.today())
    janela.mostrar_pagina("estatisticas")
    pag = janela.pagina_estatisticas
    assert pag.numeros["concluidas_hoje"].text() == "1"
    assert pag.numeros["pendentes"].text() == "1"
    assert pag.numeros["foco_hoje"].text() == "30 min"
    assert pag.g_habitos.itens and pag.g_listas.itens
    for i in range(pag.combo.count()):
        pag.combo.setCurrentIndex(i)
        assert len(pag.g_tarefas.dados) == pag.combo.currentData()
    assert not pag.grab().isNull()


# ---------- painel de detalhe ----------
def abrir(janela, titulo="Tarefa X", **campos):
    t = janela.servico.adicionar_rapido(titulo)
    for k, v in campos.items():
        setattr(t, k, v)
    janela.servico.salvar(t)
    janela.selecionar_lista(TODAS)
    janela.atualizar(selecionar_id=t.id)
    return t


def recarregar(janela, t):
    return janela.servico.banco.obter_tarefa(t.id)


def test_detalhe_periodo_duracao_tipo_secao(janela):
    t = abrir(janela, prazo=date.today() + timedelta(days=4))
    d = janela.detalhe
    d.tem_inicio.setChecked(True)
    d.inicio.setDate(d.prazo.date().addDays(-2))
    salvo = recarregar(janela, t)
    assert salvo.inicio == salvo.prazo - timedelta(days=2)
    d.tem_hora.setChecked(True)
    d.duracao.setCurrentIndex(d.duracao.findData(90))
    assert recarregar(janela, t).duracao_min == 90
    d.tipo.setCurrentIndex(d.tipo.findData("nota"))
    assert recarregar(janela, t).eh_nota
    d.secao.setEditText("Fazendo")
    d.secao.lineEdit().editingFinished.emit()
    assert recarregar(janela, t).secao == "Fazendo"
    d.tem_inicio.setChecked(False)
    assert recarregar(janela, t).inicio is None


def test_detalhe_repeticao_personalizada(janela, monkeypatch):
    t = abrir(janela, prazo=date.today())

    class Falso:
        def __init__(self, parent, regra=None):
            self.regra = regra

        def exec(self):
            return QDialog.Accepted

        def resultado(self):
            return "FREQ=DAILY;INTERVAL=3"

    monkeypatch.setattr(janela_mod, "DialogoRepeticao", Falso)
    d = janela.detalhe
    d.repetir.setCurrentIndex(d.repetir.findData(PERSONALIZAR))
    assert recarregar(janela, t).repeticao == "FREQ=DAILY;INTERVAL=3"
    assert d.repetir.currentData() == "FREQ=DAILY;INTERVAL=3"

    class Cancela(Falso):
        def exec(self):
            return QDialog.Rejected

    monkeypatch.setattr(janela_mod, "DialogoRepeticao", Cancela)
    d.repetir.setCurrentIndex(d.repetir.findData(PERSONALIZAR))
    assert recarregar(janela, t).repeticao == "FREQ=DAILY;INTERVAL=3"       # cancelar não muda


def test_detalhe_comentarios(janela):
    t = abrir(janela)
    d = janela.detalhe
    d.novo_coment.setText("Falar com a professora")
    d.novo_coment.returnPressed.emit()
    assert d.coment_caixa.count() == 1 and d.rot_coment.text().endswith("1")
    assert janela.servico.comentarios.quantidade(t.id) == 1
    uuid = janela.servico.comentarios.listar(t.id)[0].uuid
    d._apagar_comentario(uuid)
    assert d.coment_caixa.count() == 0


def test_detalhe_anexos(janela, tmp_path):
    t = abrir(janela)
    arq = tmp_path / "edital.txt"
    arq.write_text("conteúdo")
    d = janela.detalhe
    d.anexar(str(arq))
    assert d.anexos_caixa.count() == 1 and "edital.txt" in [
        w.text() for w in d.anexos_caixa.itemAt(0).widget().findChildren(type(d.btn_anexar))][0]
    anexo = janela.servico.anexos.listar(t.id)[0]
    assert os.path.exists(anexo.caminho)
    d._remover_anexo(anexo.id)
    assert d.anexos_caixa.count() == 0 and not os.path.exists(anexo.caminho)


def test_detalhe_sem_pasta_de_dados_esconde_anexos(app):
    j = JanelaPrincipal(Servico(Banco(":memory:")), notificador=lambda *_: None, prefs={})
    j.show()
    t = j.servico.adicionar_rapido("Algo")
    j.selecionar_lista(TODAS)
    j.atualizar(selecionar_id=t.id)
    assert not j.detalhe.btn_anexar.isVisibleTo(j.detalhe)


def test_detalhe_mostra_tempo_de_foco(janela):
    from norteia.core.foco import Sessao
    t = abrir(janela)
    janela.servico.foco.registrar(Sessao(datetime.now(), 3600, tarefa_uuid=t.uuid))
    janela.atualizar(selecionar_id=t.id)
    assert "1 h 00 min" in janela.detalhe.rot_foco.text()


def test_modelos_pela_janela(janela):
    svc = janela.servico
    pai = abrir(janela, "Mudança", prazo=date.today() + timedelta(days=3))
    svc.adicionar_subtarefa(pai.id, "Caixas")
    janela.salvar_modelo(pai.id, "Mudança padrão")
    m = svc.modelos.listar()[0]
    assert m.nome == "Mudança padrão"
    janela.criar_de_modelo(m.uuid)
    copias = [t for t in svc.listar(TODAS) if t.titulo == "Mudança" and t.id != pai.id]
    assert len(copias) == 1 and len(svc.subtarefas(copias[0].id)) == 1
    assert janela.id_selecionado() == copias[0].id


def test_menu_da_tarefa_tem_foco_e_modelo(janela):
    t = abrir(janela)
    textos = [a.text() for a in janela.menu_da_tarefa_id(t.id, QPoint(0, 0), executar=False).actions()]
    assert {"Concluir", "Duplicar", "Iniciar foco", "Salvar como modelo..."} <= set(textos)
    janela.servico.apagar(t.id)
    textos = [a.text() for a in janela.menu_da_tarefa_id(t.id, QPoint(0, 0), executar=False).actions()]
    assert textos == ["Restaurar da lixeira"]


# ---------- barra lateral ----------
def test_pastas_de_listas_na_barra(janela):
    svc = janela.servico
    a, b = svc.criar_projeto("Cálculo"), svc.criar_projeto("Escritório")
    janela.pasta_do_projeto(a.id, "Faculdade")
    nomes = nomes_da_barra(janela)
    i = nomes.index(("cabecalho", "Faculdade"))
    assert nomes[i + 1] == ("projeto", "Cálculo")
    assert nomes.index(("projeto", "Escritório")) < i
    janela.pasta_do_projeto(a.id, "")
    assert ("cabecalho", "Faculdade") not in nomes_da_barra(janela)


# ---------- seleção ----------
def test_selecao_sobrevive_a_atualizar_em_outras_telas(janela):
    t = abrir(janela, prazo=date.today())
    janela.mostrar_pagina("calendario")
    janela.selecionar_tarefa(t.id)
    janela.atualizar(manter_selecao=True)
    assert janela.id_selecionado() == t.id and janela.detalhe.tarefa.id == t.id
    janela.servico.apagar(t.id)
    janela.atualizar(manter_selecao=True)
    assert janela.id_selecionado() is None and janela.detalhe.tarefa is None


# ---------- diálogos ----------
def test_dialogo_dados_exporta_e_importa(janela, tmp_path):
    from norteia.ui.dialogos import DialogoDados
    svc = janela.servico
    svc.adicionar_rapido("Para o backup amanhã às 10h")
    mudou = []
    d = DialogoDados(janela, svc, ao_mudar=lambda: mudou.append(1))
    for ext, f in (("json", d.exportar_backup), ("csv", d.exportar_csv), ("ics", d.exportar_ics)):
        caminho = str(tmp_path / f"saida.{ext}")
        assert f(caminho) == caminho and os.path.getsize(caminho) > 0
    novo = Servico(Banco(":memory:"))
    d2 = DialogoDados(janela, novo, ao_mudar=lambda: mudou.append(2))
    d2.importar_backup(str(tmp_path / "saida.json"))
    assert [t.titulo for t in novo.listar(TODAS)] == ["Para o backup"] and 2 in mudou
    assert "tarefa" in d2.status.text().lower()


def test_dialogo_assinaturas_com_download_falso(janela):
    from norteia.ui.dialogos import DialogoAssinaturas
    dia = date.today() + timedelta(days=1)
    ics = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:1@x\r\nSUMMARY:Feriado\r\n"
           f"DTSTART;VALUE=DATE:{dia:%Y%m%d}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
    d = DialogoAssinaturas(janela, janela.servico, baixar_fn=lambda url: ics, em_thread=False)
    d.adicionar("Feriados", "https://exemplo.com/c.ics")
    assert d.mudou and "1 evento" in d.status.text()
    oc = janela.servico.calendario.ocorrencias(dia, dia)
    assert [(o.titulo, o.externo) for o in oc] == [("Feriado", True)]
    d2 = DialogoAssinaturas(janela, janela.servico, baixar_fn=lambda url: (_ for _ in ()).throw(OSError("sem rede")),
                            em_thread=False)
    d2.atualizar_todos()
    assert "sem rede" in d2.status.text()


def test_dialogos_de_habito_e_contagem(app):
    from norteia.ui.dialogos import DialogoContagem, DialogoHabito, DialogoRepeticao
    d = DialogoHabito(None)
    d.nome.setText("Correr")
    d.meta.setValue(2)
    r = d.resultado()
    assert r["nome"] == "Correr" and r["meta"] == 2 and r["dias"] == list(range(7)) and r["lembrete"] is None
    c = DialogoContagem(None)
    c.nome.setText("Viagem")
    assert c.resultado()["nome"] == "Viagem" and not c.resultado()["anual"]
    rep = DialogoRepeticao(None, "FREQ=WEEKLY;BYDAY=MO,WE")
    assert rep.resultado() == "FREQ=WEEKLY;BYDAY=MO,WE"


# ---------- Claude e tarefa rápida ----------
def test_sugerir_subtarefas_com_claude(janela, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    t = abrir(janela, "Preparar audiência")
    janela._ia_em_thread = False
    chamadas = []

    def falso(titulo, notas, chave, modelo):
        chamadas.append((titulo, chave, modelo))
        return ["Reunir provas", "Revisar petição"]

    janela._ia_quebrar = falso
    janela.prefs.update({"claude_api_key": "sk-x", "claude_modelo": "m1"})
    janela.detalhe.btn_ia.click()
    assert chamadas == [("Preparar audiência", "sk-x", "m1")]
    assert [s.titulo for s in janela.servico.subtarefas(t.id)] == ["Reunir provas", "Revisar petição"]
    assert janela.detalhe.btn_ia.isEnabled() and janela.detalhe.btn_ia.text().startswith("Sugerir")


def test_sugerir_subtarefas_sem_chave_nao_envia_nada(janela, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    avisou = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: avisou.append(a[2]))
    t = abrir(janela)
    janela._ia_em_thread = False
    janela._ia_quebrar = lambda *a: pytest.fail("não deveria chamar a API")
    janela.sugerir_subtarefas(t.id)
    assert avisou and "chave" in avisou[0].lower()


def test_erro_da_api_vira_aviso(janela, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from norteia.core.ia import ErroIA
    avisou = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisou.append(a[2]))
    t = abrir(janela)
    janela._ia_em_thread = False
    janela.prefs["claude_api_key"] = "k"

    def falha(*a):
        raise ErroIA("sem rede")

    janela._ia_quebrar = falha
    janela.sugerir_subtarefas(t.id)
    assert avisou == ["sem rede"] and janela.servico.subtarefas(t.id) == []
    assert janela.detalhe.btn_ia.isEnabled()


def test_janela_rapida_cria_tarefa_na_caixa(janela):
    jr = janela.janela_rapida
    janela.abrir_tarefa_rapida()
    assert jr.isVisible() and jr.campo.text() == ""
    jr.campo.setText("Ligar para o cartório amanhã às 9h !2")
    jr.campo.returnPressed.emit()
    t = [x for x in janela.servico.listar(TODAS) if x.titulo == "Ligar para o cartório"][0]
    assert t.prazo == date.today() + timedelta(days=1) and t.prazo_hora == time(9, 0)
    assert int(t.prioridade) == 2
    assert not jr.isVisible()
    assert jr.adicionar() is None                       # vazio não cria nada


def test_atalho_global_so_registra_no_windows(app):
    import sys
    from norteia.ui.atalho_global import FiltroDeAtalho
    f = FiltroDeAtalho(lambda: None)
    if not sys.platform.startswith("win"):
        assert f.registrar() is False and not f.registrado
    f.liberar()
