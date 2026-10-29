import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import fields

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from norteia.core import Banco, Servico
from norteia.ui import estacoes, tema
from norteia.ui.configuracoes import SECOES, JanelaConfiguracoes
from norteia.ui.janela import JanelaPrincipal


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def nova_janela(prefs=None, salvo=None):
    j = JanelaPrincipal(Servico(Banco(":memory:")), prefs=prefs if prefs is not None else {},
                        ao_salvar_prefs=(lambda p: salvo.update(p)) if salvo is not None else None)
    j.show()
    return j


# ---------- paletas ----------
def test_o_tema_padrao_escuro_continua_igual_ao_original():
    p = tema.paleta("padrao", True)
    assert (p.fundo, p.barra, p.trilho, p.campo, p.destaque, p.texto, p.apagado) == (
        "#1c1c1c", "#212121", "#181818", "#272727", "#4772fa", "#e8e8e8", "#8c8c8c")


@pytest.mark.parametrize("cor", [c.chave for c in tema.CORES])
@pytest.mark.parametrize("escuro", [True, False])
def test_toda_paleta_e_legivel(cor, escuro):
    p = tema.paleta(cor, escuro)
    assert p.escuro is escuro
    assert tema.contraste(p.texto, p.fundo) >= 7
    assert tema.contraste(p.apagado, p.fundo) >= 4.5
    assert tema.contraste(p.destaque, p.fundo) >= 3
    assert tema.contraste(p.sobre_destaque, p.destaque) >= 4
    assert tema.contraste(p.vermelho, p.fundo) >= 4.4


@pytest.mark.parametrize("cor", [c.chave for c in tema.CORES])
@pytest.mark.parametrize("escuro", [True, False])
def test_cores_da_paleta_nao_se_confundem(cor, escuro):
    """A troca ao vivo troca cor por cor; duas funções diferentes não podem ter o mesmo valor."""
    p = tema.paleta(cor, escuro)
    vistos: dict[str, str] = {}
    permitidos = {frozenset({"fundo", "painel"}), frozenset({"destaque", "prioridade1"}),
                  frozenset({"vermelho", "prioridade3"})}
    for f in fields(p):
        if f.name in ("nome", "escuro", "seta", "seta_cima", "marca"):
            continue
        v = getattr(p, f.name)
        itens = [(f"{f.name}{i}", x) for i, x in enumerate(v)] if isinstance(v, tuple) else [(f.name, v)]
        for nome, x in itens:
            x = x.lower()
            if x in vistos:
                assert frozenset({vistos[x], nome}) in permitidos, (vistos[x], nome, x)
            vistos[x] = nome


def test_trocar_cores_nao_encadeia_e_ignora_maiusculas():
    assert tema.trocar_cores("a:#AAA; b:#bbb; c:#ccc", {"#aaa": "#bbb", "#bbb": "#ccc"}) == "a:#bbb; b:#ccc; c:#ccc"
    assert tema.trocar_cores("x", {}) == "x"


def test_modo_segue_o_sistema(monkeypatch):
    monkeypatch.setattr(tema, "escuro_do_sistema", lambda: False)
    assert tema.da_preferencia({"tema_modo": "sistema"}).escuro is False
    monkeypatch.setattr(tema, "escuro_do_sistema", lambda: True)
    assert tema.da_preferencia({"tema_modo": "sistema"}).escuro is True
    assert tema.da_preferencia({"tema_modo": "claro"}).escuro is False
    assert tema.da_preferencia({}).escuro is True
    assert tema.da_preferencia({"tema_cor": "inexistente"}).nome == "padrao-escuro"


# ---------- troca ao vivo ----------
def perto(a: str, b: str) -> bool:
    return all(abs(int(a[k:k + 2], 16) - int(b[k:k + 2], 16)) <= 3 for k in (1, 3, 5))


def cor_do_botao(botao):
    img = botao.icon().pixmap(botao.iconSize()).toImage().convertToFormat(QImage.Format_ARGB32)
    melhor = max((img.pixelColor(x, y) for x in range(img.width()) for y in range(img.height())),
                 key=lambda c: c.alpha())
    return melhor.name()


def test_trocar_o_tema_muda_estilo_icones_e_volta_ao_original(app):
    salvo = {}
    j = nova_janela(salvo=salvo)
    original = j.styleSheet()
    estilo_vazio = j.vazio_cartao.styleSheet()
    assert perto(cor_do_botao(j.btn_config), tema.paleta("padrao", True).texto)
    j.aplicar_preferencias({"tema_cor": "lilas", "tema_modo": "claro"})
    claro = tema.paleta("lilas", False)
    assert tema.atual.nome == "lilas-claro"
    assert j.styleSheet() == tema.qss() and claro.fundo in j.styleSheet()
    assert claro.apagado in j.vazio_cartao.styleSheet()            # estilo que foi montado com a cor antiga
    assert perto(cor_do_botao(j.btn_config), claro.texto)          # ícone recolorido
    assert salvo["tema_cor"] == "lilas"
    j.aplicar_preferencias({"tema_cor": "padrao", "tema_modo": "escuro"})
    assert tema.atual.nome == "padrao-escuro"
    assert j.styleSheet() == original
    assert j.vazio_cartao.styleSheet() == estilo_vazio
    assert perto(cor_do_botao(j.btn_config), tema.paleta("padrao", True).texto)


def test_tela_inteira_em_cada_tema_sem_quebrar(app):
    j = nova_janela()
    for chave in [c.chave for c in tema.CORES]:
        for modo in ("claro", "escuro"):
            j.aplicar_preferencias({"tema_cor": chave, "tema_modo": modo})
            for pagina in ("tarefas", "calendario", "matriz", "foco", "habitos", "estatisticas", "ia"):
                j.mostrar_pagina(pagina)
                app.processEvents()
                j.grab()
    j.aplicar_preferencias({"tema_cor": "padrao", "tema_modo": "escuro"})


def test_fundo_ilustrado(app):
    j = nova_janela({"tema_fundo": "outono"})
    assert j.centro.estacao == "outono"
    j.aplicar_preferencias({"tema_fundo": ""})
    assert j.centro.estacao == ""
    j.aplicar_preferencias({"tema_fundo": "nao-existe"})
    assert j.centro.estacao == ""
    for chave, _ in estacoes.ESTACOES:
        j.aplicar_preferencias({"tema_fundo": chave})
        assert j.centro.estacao == chave
        j.grab()


def test_seguir_o_sistema_reage_a_mudanca(app, monkeypatch):
    j = nova_janela({"tema_modo": "sistema"})
    monkeypatch.setattr(tema, "escuro_do_sistema", lambda: False)
    j._ao_mudar_esquema_do_sistema()
    assert tema.atual.escuro is False
    monkeypatch.setattr(tema, "escuro_do_sistema", lambda: True)
    j._ao_mudar_esquema_do_sistema()
    assert tema.atual.escuro is True
    j.prefs["tema_modo"] = "claro"
    j._ao_mudar_esquema_do_sistema()               # fora do modo "sistema" não mexe
    assert tema.atual.escuro is True
    j.aplicar_preferencias({"tema_modo": "escuro"})


# ---------- janela de configurações ----------
def test_configuracoes_tem_as_secoes_e_abre_na_pedida(app):
    j = nova_janela()
    d = JanelaConfiguracoes(j, "sobre")
    assert [d.nav.item(i).text() for i in range(d.nav.count())] == [n for _, n, _ in SECOES]
    assert d.pilha.currentIndex() == [c for c, _, _ in SECOES].index("sobre")
    d.mostrar_secao("aparencia")
    assert d.nav.currentRow() == [c for c, _, _ in SECOES].index("aparencia")
    d.mostrar_secao("nao-existe")
    assert d.nav.currentRow() == [c for c, _, _ in SECOES].index("aparencia")


def test_aparencia_escolhe_modo_cor_e_fundo_na_hora(app):
    salvo = {}
    j = nova_janela(salvo=salvo)
    d = JanelaConfiguracoes(j, "aparencia")
    d.btns_modo["claro"].click()
    assert j.prefs["tema_modo"] == "claro" and tema.atual.escuro is False
    d.amostras["rosa"].click()
    assert j.prefs["tema_cor"] == "rosa" and tema.atual.nome == "rosa-claro"
    assert d.amostras["rosa"].isChecked() and not d.amostras["padrao"].isChecked()
    d.miniaturas["inverno"].click()
    assert j.centro.estacao == "inverno" and d.miniaturas["inverno"].isChecked()
    d.miniaturas[""].click()
    assert j.centro.estacao == ""
    d.grab()
    assert salvo["tema_cor"] == "rosa"
    j.aplicar_preferencias({"tema_cor": "padrao", "tema_modo": "escuro"})


def test_geral_nome_do_avatar_e_painel_lateral(app):
    j = nova_janela()
    d = JanelaConfiguracoes(j, "geral")
    d.campo_nome.setText("Maria")
    d.campo_nome.editingFinished.emit()
    assert j.prefs["nome_usuario"] == "Maria"
    d.sw_lateral.setChecked(True)
    assert j.prefs["detalhe_lateral"] is True
    d.sw_bandeja.setChecked(False)
    assert j.prefs["fechar_para_bandeja"] is False


def test_icone_de_duas_cores_e_recolorido_inteiro(app):
    """O ícone de Tarefas é um quadrado cheio com um "certo" de outra cor: as duas cores trocam."""
    from norteia.ui import retema
    j = nova_janela()
    botao = j.btns_pagina["tarefas"]
    j.aplicar_preferencias({"tema_cor": "padrao", "tema_modo": "claro"})
    claro = tema.paleta("padrao", False)
    img = botao.icon().pixmap(QSize(256, 256)).toImage().convertToFormat(QImage.Format_ARGB32)
    cores = retema._cores_do_desenho(img)
    assert len(cores) == 2
    assert any(perto(c, claro.texto) for c in cores) and any(perto(c, claro.trilho) for c in cores)
    j.aplicar_preferencias({"tema_cor": "padrao", "tema_modo": "escuro"})
