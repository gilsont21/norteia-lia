import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, datetime, time, timedelta

import pytest
from PySide6.QtWidgets import QApplication

from norteia.core import AMANHA, Banco, Servico, chave_tag
from norteia.ui.aviso import AvisoLembrete
from norteia.ui.delegados import PAPEL_CHAVE, PAPEL_TAREFA, PAPEL_TIPO
from norteia.ui.janela import JanelaPrincipal


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def janela(app):
    j = JanelaPrincipal(Servico(Banco(":memory:")), prefs={})
    j.show()
    return j


def linhas_da_barra(j):
    return [(j.barra.item(i).data(PAPEL_TIPO), j.barra.item(i).text()) for i in range(j.barra.count())]


def tarefas_na_tela(j):
    return [j.tarefas.item(i).data(PAPEL_TAREFA).titulo for i in range(j.tarefas.count())
            if j.tarefas.item(i).data(PAPEL_TAREFA) is not None]


# ---------- barra lateral ----------
def test_barra_tem_amanha(janela):
    assert ("lista", "Amanhã") in linhas_da_barra(janela)
    janela.servico.adicionar_rapido("amanhã cedo")
    janela.atualizar()
    janela.selecionar_lista(AMANHA)
    assert tarefas_na_tela(janela) == ["cedo"]


def test_renomear_e_arquivar_projeto_pela_interface(janela):
    p = janela.servico.criar_projeto("Casa")
    janela.servico.adicionar_rapido("lavar louça hoje-x", p.id)
    janela.atualizar()
    janela.renomear_projeto(p.id, "Apartamento")
    assert ("projeto", "Apartamento") in linhas_da_barra(janela)
    janela.selecionar_lista(p.id)
    janela.arquivar_projeto(p.id)
    assert ("arquivada", "Apartamento") in linhas_da_barra(janela)
    assert ("projeto", "Apartamento") not in linhas_da_barra(janela)
    assert janela.lista_atual == "hoje"          # saiu da lista que arquivou
    janela.arquivar_projeto(p.id, False)
    assert ("projeto", "Apartamento") in linhas_da_barra(janela)


def test_apagar_projeto_pela_interface(janela):
    p = janela.servico.criar_projeto("Temporária")
    t = janela.servico.adicionar_rapido("x", p.id)
    janela.selecionar_lista(p.id)
    janela.apagar_projeto(p.id, confirmar=False)
    assert janela.lista_atual == "hoje"
    assert ("projeto", "Temporária") not in linhas_da_barra(janela)
    assert janela.servico.banco.obter_tarefa(t.id).apagada_em is not None


def test_mover_projeto_para_cima_e_para_baixo(janela):
    a = janela.servico.criar_projeto("A")
    janela.servico.criar_projeto("B")
    janela.mover_projeto(a.id, +1)
    nomes = [t for tipo, t in linhas_da_barra(janela) if tipo == "projeto"]
    assert nomes == ["B", "A"]


def test_etiquetas_pela_interface(janela):
    janela.servico.adicionar_rapido("a #velha")
    janela.servico.adicionar_rapido("b #outra")
    janela.atualizar()
    janela.selecionar_lista(chave_tag("velha"))
    janela.renomear_tag("velha", "Nova")
    assert janela.lista_atual == chave_tag("nova")
    janela.trocar_cor_tag("nova", "#4dd0b1")
    assert janela.delegado.cores_tags == {"nova": "#4dd0b1"}
    janela.mesclar_tag("nova", "outra")
    assert [t for tipo, t in linhas_da_barra(janela) if tipo == "etiqueta"] == ["outra"]
    assert janela.lista_atual == chave_tag("outra")
    janela.apagar_tag("outra", confirmar=False)
    assert [t for tipo, t in linhas_da_barra(janela) if tipo == "etiqueta"] == []
    assert janela.lista_atual == "hoje"


def test_renomear_filtro(janela):
    f = janela.servico.criar_filtro("Antigo", {"prioridade_min": 2})
    janela.atualizar()
    janela.renomear_filtro(f"filtro:{f.id}", "Novo nome")
    assert ("filtro", "Novo nome") in linhas_da_barra(janela)


# ---------- ações sobre tarefas ----------
def test_duplicar_fixar_e_descartar(janela):
    t = janela.servico.adicionar_rapido("original hoje-x")
    t.prazo = date.today()
    janela.servico.salvar(t)
    janela.atualizar()
    janela.duplicar_tarefa(t.id)
    assert tarefas_na_tela(janela).count("original hoje-x") == 2
    janela.fixar_tarefa(t.id)
    assert janela.tarefas.item(0).data(PAPEL_TAREFA).id == t.id
    janela.descartar_tarefa(t.id)
    assert tarefas_na_tela(janela).count("original hoje-x") == 1
    janela.selecionar_lista("concluidas")
    assert tarefas_na_tela(janela) == ["original hoje-x"]


def test_mover_tarefa_leva_as_subtarefas(janela):
    p = janela.servico.criar_projeto("Destino")
    pai = janela.servico.adicionar_rapido("pai")
    sub = janela.servico.adicionar_subtarefa(pai.id, "filha")
    janela.mover_tarefa(pai.id, p.id)
    assert janela.servico.banco.obter_tarefa(sub.id).projeto_id == p.id


def test_atalhos_agem_na_tarefa_selecionada(janela):
    t = janela.servico.adicionar_rapido("alvo")
    t.prazo = date.today()
    janela.servico.salvar(t)
    janela.atualizar()
    janela.tarefas.setCurrentRow(0)
    janela._com_selecionada(janela.fixar_tarefa)
    assert janela.servico.banco.obter_tarefa(t.id).fixada


# ---------- agrupar ----------
def _criar_tarefas_variadas(j):
    hoje = date.today()
    casos = [("atrasada", hoje - timedelta(days=2), 3), ("tarefa-do-dia", hoje, 0),
             ("tarefa-seguinte", hoje + timedelta(days=1), 2), ("sem data", None, 1)]
    for titulo, prazo, prio in casos:
        t = j.servico.adicionar_rapido(titulo)
        t.prazo, t.prioridade = prazo, type(t.prioridade)(prio)
        j.servico.salvar(t)
    j.selecionar_lista("todas")


def cabecalhos(j):
    return [j.tarefas.item(i).text() for i in range(j.tarefas.count())
            if j.tarefas.item(i).data(PAPEL_TIPO) == "grupo"]


def test_agrupar_por_data(janela):
    _criar_tarefas_variadas(janela)
    janela.definir_agrupamento("data")
    assert cabecalhos(janela) == ["Atrasadas", "Hoje", "Amanhã", "Sem data"]
    assert tarefas_na_tela(janela) == ["atrasada", "tarefa-do-dia", "tarefa-seguinte", "sem data"]


def test_agrupar_por_prioridade_e_projeto(janela):
    _criar_tarefas_variadas(janela)
    janela.definir_agrupamento("prioridade")
    assert cabecalhos(janela) == ["Alta", "Média", "Baixa", "Nenhuma"]
    p = janela.servico.criar_projeto("Faculdade")
    t = janela.servico.adicionar_rapido("estudar", p.id)
    janela.atualizar()
    janela.definir_agrupamento("projeto")
    assert cabecalhos(janela) == ["Caixa de Entrada", "Faculdade"]


def test_agrupar_por_etiqueta(janela):
    janela.servico.adicionar_rapido("a #zeta")
    janela.servico.adicionar_rapido("b #alfa")
    janela.servico.adicionar_rapido("c")
    janela.selecionar_lista("todas")
    janela.definir_agrupamento("etiqueta")
    assert cabecalhos(janela) == ["#alfa", "#zeta", "Sem etiqueta"]


def test_agrupar_nao_quebra_selecao_nem_vazio(janela):
    janela.definir_agrupamento("data")
    assert janela.vazio.isVisible() and cabecalhos(janela) == []
    _criar_tarefas_variadas(janela)
    janela.atualizar()
    janela.tarefas.setCurrentRow(1)       # a linha 0 é cabeçalho; a 1 é uma tarefa
    assert janela.detalhe.tarefa is not None
    janela.definir_agrupamento("nenhum")
    assert cabecalhos(janela) == []


def test_fixadas_ficam_no_topo_em_qualquer_ordem(janela):
    a = janela.servico.adicionar_rapido("a")
    b = janela.servico.adicionar_rapido("b")
    janela.servico.alternar_fixada(b.id)
    janela.selecionar_lista("todas")
    for ordem in ("data", "titulo", "prioridade", "criacao", "manual"):
        janela.definir_ordem(ordem)
        assert tarefas_na_tela(janela)[0] == "b", ordem


# ---------- subtarefas em níveis ----------
def test_subtarefa_dentro_de_subtarefa_pelo_painel(janela):
    pai = janela.servico.adicionar_rapido("pai hoje-x")
    pai.prazo = date.today()
    janela.servico.salvar(pai)
    janela.atualizar()
    janela.tarefas.setCurrentRow(0)
    d = janela.detalhe
    d.nova_sub.setText("filha")
    d._adicionar_sub()
    filha = janela.servico.subtarefas(pai.id)[0]
    d._escolher_alvo(filha.id, filha.titulo)
    assert "filha" in d.nova_sub.placeholderText()
    d.nova_sub.setText("neta")
    d._adicionar_sub()
    assert [s.titulo for s in janela.servico.subtarefas(filha.id)] == ["neta"]
    d.keyPressEvent(type("E", (), {"key": lambda s: 0x01000000})())     # Esc volta ao nível de cima
    assert d._alvo_sub is None


# ---------- painel de detalhe: lembrete constante ----------
def test_lembrete_constante_salva_pelo_painel(janela):
    t = janela.servico.adicionar_rapido("reunião hoje às 10h")
    janela.atualizar()
    janela.tarefas.setCurrentRow(0)
    d = janela.detalhe
    assert d.constante.isEnabled()
    d.constante.setCurrentIndex(d.constante.findData(10))
    assert janela.servico.banco.obter_tarefa(t.id).insistir_min == 10
    d.lembrar.setCurrentIndex(0)                    # tirar o lembrete desliga a insistência
    assert janela.servico.banco.obter_tarefa(t.id).insistir_min == 0
    assert not d.constante.isEnabled()


def test_botoes_do_painel(janela):
    t = janela.servico.adicionar_rapido("x hoje-y")
    t.prazo = date.today()
    janela.servico.salvar(t)
    janela.atualizar()
    janela.tarefas.setCurrentRow(0)
    janela.detalhe.btn_fixar.click()
    assert janela.servico.banco.obter_tarefa(t.id).fixada
    assert janela.detalhe.btn_fixar.text() == "Desafixar"
    janela.detalhe.btn_descartar.click()
    assert janela.servico.banco.obter_tarefa(t.id).descartada


# ---------- avisos de lembrete ----------
def _com_lembrete(j, hora=time(10, 0)):
    t = j.servico.adicionar_rapido("Reunião")
    t.prazo, t.prazo_hora, t.lembretes = date(2026, 10, 26), hora, [0]
    return j.servico.salvar(t)


def test_aviso_aparece_com_concluir_e_adiar(janela):
    t = _com_lembrete(janela)
    janela.verificar_lembretes(datetime(2026, 10, 26, 10, 0))
    assert len(janela.avisos.avisos) == 1
    aviso = janela.avisos.avisos[0]
    assert aviso.tarefa_id == t.id and aviso.rotulo_titulo.text() == "Reunião"
    janela.avisos.avisos[0].btn_concluir.click()
    assert janela.servico.banco.obter_tarefa(t.id).concluida
    assert janela.avisos.avisos == []


def test_aviso_adiar_cria_soneca(janela):
    t = _com_lembrete(janela)
    janela.verificar_lembretes(datetime(2026, 10, 26, 10, 0))
    aviso = janela.avisos.avisos[0]
    aviso.menu_adiar.actions()[1].trigger()            # "10 minutos"
    assert [tid for tid, _ in janela.servico.banco.sonecas()] == [t.id]
    assert janela.avisos.avisos == []


def test_aviso_amanha_de_manha(janela):
    t = _com_lembrete(janela)
    janela.verificar_lembretes(datetime(2026, 10, 26, 10, 0))
    janela.avisos.avisos[0].menu_adiar.actions()[-1].trigger()
    [(tid, ate)] = janela.servico.banco.sonecas()
    assert ate.time() == time(9, 0) and ate.date() > date.today() - timedelta(days=1)


def test_aviso_repetido_substitui_o_anterior(janela):
    t = janela.servico.adicionar_rapido("x")
    janela.avisos.mostrar(t.id, "x", "primeiro", exibir=False)
    janela.avisos.mostrar(t.id, "x", "segundo", exibir=False)
    assert len(janela.avisos.avisos) == 1 and janela.avisos.avisos[0].rotulo_texto.text() == "segundo"


def test_aviso_desligado_usa_notificador_simples(app):
    recebidos = []
    j = JanelaPrincipal(Servico(Banco(":memory:")), prefs={"aviso_na_tela": False},
                        notificador=lambda titulo, texto: recebidos.append((titulo, texto)))
    _com_lembrete(j)
    j.verificar_lembretes(datetime(2026, 10, 26, 10, 0))
    assert recebidos == [("Reunião", "Vence agora")] and j.avisos.avisos == []


def test_menu_da_tarefa_adiar_pelo_metodo(janela):
    t = janela.servico.adicionar_rapido("lembrar")
    janela.adiar_tarefa(t.id, 30)
    assert [tid for tid, _ in janela.servico.banco.sonecas()] == [t.id]


# ---------- resumo e preferências ----------
def test_resumo_diario_pela_janela(app):
    recebidos = []
    j = JanelaPrincipal(Servico(Banco(":memory:")),
                        notificador=lambda titulo, texto: recebidos.append((titulo, texto)),
                        prefs={"resumo_diario": True, "resumo_hora": "08:00"})
    t = j.servico.adicionar_rapido("do dia")
    t.prazo = date.today()
    j.servico.salvar(t)
    j.verificar_lembretes(datetime.combine(date.today(), time(9, 0)))
    j.verificar_lembretes(datetime.combine(date.today(), time(9, 5)))
    assert recebidos == [("Resumo do dia", "Você tem 1 tarefa para hoje.")]


def test_preferencias_sao_salvas(app):
    salvo = {}
    j = JanelaPrincipal(Servico(Banco(":memory:")), prefs={}, ao_salvar_prefs=lambda p: salvo.update(p))
    j.aplicar_preferencias({"resumo_diario": False, "resumo_hora": "07:30"})
    assert salvo == {"resumo_diario": False, "resumo_hora": "07:30"}


def test_janela_de_configuracoes_grava_na_hora(app):
    from norteia.ui.configuracoes import JanelaConfiguracoes
    salvo = {}
    j = JanelaPrincipal(Servico(Banco(":memory:")), prefs={"resumo_hora": "07:15"}, ao_salvar_prefs=lambda p: salvo.update(p))
    d = JanelaConfiguracoes(j, "notificacoes")
    assert d.pilha.currentIndex() == 1
    assert d.hora_resumo.time().toString("HH:mm") == "07:15"
    d.sw_aviso.setChecked(False)
    d.sw_resumo.setChecked(False)
    d.hora_resumo.setTime(d.hora_resumo.time().addSecs(15 * 60))
    assert j.prefs["aviso_na_tela"] is False and j.prefs["resumo_diario"] is False
    assert j.prefs["resumo_hora"] == "07:30" and salvo["resumo_hora"] == "07:30"


# ---------- bandeja do sistema e abrir com o Windows ----------
class _AutostartFalso:
    def __init__(self):
        self.valor = None

    def definir(self, sim):
        self.valor = sim


def test_fechar_a_janela_esconde_quando_a_bandeja_esta_ligada(app):
    j = JanelaPrincipal(Servico(Banco(":memory:")), prefs={"fechar_para_bandeja": True, "aviso_bandeja_visto": True})
    j._bandeja_disponivel = lambda: True
    j.show()
    assert j.close() is False                   # o evento foi ignorado: a janela só some
    assert not j.isVisible()
    assert j._bandeja is not None


def test_sem_bandeja_no_sistema_fechar_fecha_de_verdade(app):
    j = JanelaPrincipal(Servico(Banco(":memory:")), prefs={"fechar_para_bandeja": True})
    j._bandeja_disponivel = lambda: False
    j.show()
    assert j.close() is True
    assert j._bandeja is None


def test_opcao_desligada_fecha_normalmente(app):
    j = JanelaPrincipal(Servico(Banco(":memory:")), prefs={"fechar_para_bandeja": False})
    j.show()
    assert j.close() is True


def test_sair_pelo_menu_da_bandeja_encerra(app):
    j = JanelaPrincipal(Servico(Banco(":memory:")), prefs={"fechar_para_bandeja": True, "aviso_bandeja_visto": True})
    j._bandeja_disponivel = lambda: True
    j.show()
    j.sair()
    assert j._saindo and not j.isVisible()


def test_primeiro_fechamento_avisa_uma_vez_e_grava(app):
    salvo = {}
    j = JanelaPrincipal(Servico(Banco(":memory:")), prefs={"fechar_para_bandeja": True},
                        ao_salvar_prefs=lambda p: salvo.update(p))
    j._bandeja_disponivel = lambda: True
    j.show()
    j.close()
    assert salvo.get("aviso_bandeja_visto") is True


def test_restaurar_traz_a_janela_de_volta(app):
    j = JanelaPrincipal(Servico(Banco(":memory:")), prefs={"fechar_para_bandeja": True, "aviso_bandeja_visto": True})
    j._bandeja_disponivel = lambda: True
    j.show()
    j.close()
    j.restaurar()
    assert j.isVisible()


def test_iniciar_na_bandeja_nao_mostra_a_janela(app):
    j = JanelaPrincipal(Servico(Banco(":memory:")), prefs={})
    j._bandeja_disponivel = lambda: True
    j.iniciar_na_bandeja()
    assert not j.isVisible() and j._bandeja is not None


def test_preferencia_abrir_com_o_windows_chama_o_registro(app):
    j = JanelaPrincipal(Servico(Banco(":memory:")), prefs={})
    falso = _AutostartFalso()
    j._autostart = falso
    j.aplicar_preferencias({"iniciar_com_windows": True})
    assert falso.valor is True
    j.aplicar_preferencias({"resumo_diario": False})        # não mexe no registro
    assert falso.valor is True


def test_autostart_grava_e_remove_a_entrada(tmp_path):
    from PySide6.QtCore import QSettings
    from norteia import autostart
    cfg = QSettings(str(tmp_path / "run.ini"), QSettings.IniFormat)
    assert not autostart.ligado(cfg)
    autostart.definir(True, cfg, linha='"C:\\App\\Norteia.exe" --minimizado')
    assert autostart.ligado(cfg)
    assert cfg.value("Norteia Lia") == '"C:\\App\\Norteia.exe" --minimizado'
    autostart.definir(False, cfg)
    assert not autostart.ligado(cfg)


def test_autostart_reconhece_e_limpa_a_entrada_do_nome_antigo(tmp_path):
    from PySide6.QtCore import QSettings
    from norteia import autostart
    cfg = QSettings(str(tmp_path / "run2.ini"), QSettings.IniFormat)
    cfg.setValue("Tarefas", '"C:\\Velho\\Tarefas.exe" --minimizado')
    assert autostart.ligado(cfg)                      # versão antiga já instalada continua valendo
    autostart.definir(True, cfg, linha='"C:\\Novo\\Norteia.exe" --minimizado')
    assert not cfg.contains("Tarefas") and cfg.contains("Norteia Lia")
    autostart.definir(False, cfg)
    assert not cfg.contains("Norteia Lia") and not autostart.ligado(cfg)


def test_comando_do_autostart_abre_minimizado_e_sem_terminal():
    from norteia import autostart
    linha = autostart.comando("C:\\Python\\python.exe")
    assert linha.startswith('"C:\\Python\\pythonw.exe"') and linha.endswith("--minimizado")
    assert "main.py" in linha
