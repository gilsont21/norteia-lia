"""Compromissos no mesmo horário se sobrepõem como no Google Agenda (o menor por cima)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, time
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from norteia.core.calendario import Ocorrencia
from norteia.ui.pagina_calendario import GradeHoras

LARGURA = 200.0


def oc(titulo, h, m, dur):
    return Ocorrencia(titulo, date(2026, 10, 27), date(2026, 10, 27), time(h, m), dur, "#e0b040")


def camadas(*itens):
    eu = SimpleNamespace(RECUO_MIN=GradeHoras.RECUO_MIN)
    return {o.titulo: (e, d, c) for o, e, d, c in GradeHoras._camadas(eu, list(itens), LARGURA)}


def test_sem_cruzamento_ocupa_a_largura_toda():
    r = camadas(oc("A", 8, 0, 60), oc("B", 10, 0, 60))
    assert r["A"] == r["B"] and r["A"][2] == 0
    assert r["A"][1] - r["A"][0] > LARGURA - 10


def test_menor_dentro_do_maior_fica_por_cima_e_recuado():
    r = camadas(oc("Estágio", 8, 0, 240), oc("Inglês", 10, 0, 60))
    (ea, da, ca), (eb, db, cb) = r["Estágio"], r["Inglês"]
    assert ca == 0 and cb == 1                       # o menor vem depois na pintura (por cima)
    assert eb > ea and eb - ea <= 14                 # recuo curto, não metade da largura
    assert da == db                                  # os dois vão até a borda direita
    assert db - eb > LARGURA * 0.6                   # continua largo e legível


def test_comecam_juntos_o_menor_vai_para_a_direita_e_o_maior_ganha_folga():
    r = camadas(oc("Estágio", 14, 0, 240), oc("Inglês", 14, 0, 60))
    (ea, da, ca), (eb, db, cb) = r["Estágio"], r["Inglês"]
    assert ca == 0 and cb == 1
    assert eb > ea + (LARGURA * 0.3)                 # começa lá pela metade
    assert da < db                                   # o grande não vai até a borda: sobra a faixa do menor
    assert eb < da                                   # mas se cruzam: o menor está sobre o grande


def test_tres_niveis_formam_escada():
    r = camadas(oc("A", 8, 0, 240), oc("B", 10, 0, 90), oc("C", 10, 30, 30))
    assert r["A"][2] == 0 and r["B"][2] == 1 and r["C"][2] == 2
    assert r["A"][0] < r["B"][0] < r["C"][0]


def test_dois_seguidos_dentro_do_maior_ficam_na_mesma_camada():
    r = camadas(oc("A", 8, 0, 240), oc("B", 9, 0, 60), oc("C", 11, 0, 60))
    assert r["B"][2] == r["C"][2] == 1 and r["B"][0] == r["C"][0]


def test_nunca_fica_estreito_demais():
    itens = [oc("A", 8, 0, 300)] + [oc(f"X{i}", 8, 0, 60 + i) for i in range(1, 6)]
    for e, d, _c in camadas(*itens).values():
        assert d - e >= 24


def test_pintura_de_baixo_para_cima():
    eu = SimpleNamespace(RECUO_MIN=12)
    ordem = [c for _o, _e, _d, c in GradeHoras._camadas(eu, [oc("B", 10, 0, 60), oc("A", 8, 0, 240)], LARGURA)]
    assert ordem == sorted(ordem)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_grade_desenha_e_clica_no_de_cima(app):
    from norteia.core import Banco, Servico
    from norteia.ui.janela import JanelaPrincipal
    svc = Servico(Banco(":memory:"))
    from norteia.core.models import Tarefa
    hoje = date.today()
    a = svc.salvar(Tarefa(titulo="Estágio", prazo=hoje, prazo_hora=time(8, 0), duracao_min=240, ordem=1))
    b = svc.salvar(Tarefa(titulo="Aula de inglês", prazo=hoje, prazo_hora=time(10, 0), duracao_min=60, ordem=2))
    j = JanelaPrincipal(svc, notificador=lambda t, x: None, prefs={}, google_em_thread=False)
    j.resize(1300, 800)
    j.show()
    j.mostrar_pagina("calendario")
    pc = j.pagina_calendario
    pc.definir_modo("dia")
    app.processEvents()
    grade = next(g for g in pc.findChildren(GradeHoras) if g.isVisible())
    grade.grab()
    topo = {o.titulo: r for r, o, _d in grade.hits}
    assert set(topo) >= {"Estágio", "Aula de inglês"}
    centro = topo["Aula de inglês"].center()
    achou = [o.titulo for r, o, _d in reversed(grade.hits) if r.contains(centro)]
    assert achou[0] == "Aula de inglês"              # o clique vai para o que está por cima
