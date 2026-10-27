"""Gera capturas de tela da interface sem abrir janela (modo offscreen).

Uso: python tools/capturar.py <pasta_saida>
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date, datetime, time  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

from norteia.core import Banco, Servico  # noqa: E402
from norteia.demo import popular  # noqa: E402
from norteia.ui.delegados import PAPEL_TAREFA  # noqa: E402
from norteia.ui.janela import JanelaPrincipal  # noqa: E402


def main(saida: Path) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    svc = Servico(Banco(":memory:"))
    popular(svc)
    j = JanelaPrincipal(svc)
    j.resize(1360, 1000)
    j.show()
    app.processEvents()

    def foto(nome: str):
        app.processEvents()
        j.grab().save(str(saida / nome))

    j.selecionar_lista("hoje")
    j.tarefas.setCurrentRow(0)
    foto("1-hoje-detalhe.png")
    for i in range(j.tarefas.count()):
        if j.tarefas.item(i).data(PAPEL_TAREFA).titulo.startswith("Academia"):
            j.tarefas.setCurrentRow(i)
    foto("2-repeticao-e-lembrete.png")
    for i in range(j.tarefas.count()):
        if j.tarefas.item(i).data(PAPEL_TAREFA).titulo.startswith("Estudar para"):
            j.tarefas.setCurrentRow(i)
    foto("6-subtarefas.png")
    j.selecionar_lista("filtro:1")
    foto("7-filtro-salvo.png")
    j.definir_ordem("manual")
    j.selecionar_lista("proximos")
    foto("8-ordem-manual.png")
    j.definir_ordem("data")
    j.selecionar_lista("caixa")
    foto("3-caixa-de-entrada.png")
    j.selecionar_lista("tag:si601")
    foto("4-etiqueta.png")
    j.selecionar_lista("concluidas")
    foto("5-concluidas.png")

    # ---- etapa 6 ----
    j.selecionar_lista("todas")
    j.definir_agrupamento("data")
    foto("9-agrupado-por-data.png")
    j.definir_agrupamento("nenhum")
    j.selecionar_lista("hoje")
    for i in range(j.tarefas.count()):
        t = j.tarefas.item(i).data(PAPEL_TAREFA)
        if t is not None and t.titulo.startswith("Reunião com a orientadora"):
            j.tarefas.setCurrentRow(i)
    foto("10-lembrete-constante.png")
    for i in range(j.tarefas.count()):
        t = j.tarefas.item(i).data(PAPEL_TAREFA)
        if t is not None and t.titulo.startswith("Estudar para"):
            j.tarefas.setCurrentRow(i)
    foto("11-fixada-e-subtarefas-em-niveis.png")
    j.verificar_lembretes(datetime.combine(date.today(), time(23, 59)))
    app.processEvents()
    if j.avisos.avisos:
        j.avisos.avisos[0].grab().save(str(saida / "12-aviso-de-lembrete.png"))
        for a in list(j.avisos.avisos):
            a.fechar()

    # ---- etapas 7 e 8 ----
    j.mostrar_pagina("calendario")
    for modo, nome in (("semana", "13-calendario-semana"), ("mes", "14-calendario-mes"),
                       ("dia", "15-calendario-dia"), ("agenda", "16-calendario-agenda")):
        j.pagina_calendario.definir_modo(modo)
        foto(nome + ".png")
    j.mostrar_pagina("tarefas")
    j.selecionar_lista("todas")
    j.definir_visao("kanban")
    j.kanban.combo.setCurrentIndex(j.kanban.combo.findData("data"))
    foto("17-kanban-por-data.png")
    j.selecionar_lista(next(p.id for p in svc.banco.listar_projetos() if p.nome == "Projetos pessoais"))
    j.kanban.combo.setCurrentIndex(j.kanban.combo.findData("secao"))
    foto("18-kanban-secoes.png")
    j.selecionar_lista("todas")
    j.definir_visao("linha_tempo")
    foto("19-linha-do-tempo.png")
    j.definir_visao("lista")
    j.mostrar_pagina("matriz")
    foto("20-matriz-eisenhower.png")
    j.mostrar_pagina("foco")
    pf = j.pagina_foco
    agora = datetime.now()
    pf._agora = lambda: agora
    pf.iniciar()
    pf.tique(agora)
    foto("21-foco.png")
    pf.parar()
    j.mostrar_pagina("habitos")
    foto("22-habitos.png")
    j.mostrar_pagina("contagem")
    foto("23-contagem-regressiva.png")
    j.mostrar_pagina("estatisticas")
    foto("24-estatisticas.png")
    j.mostrar_pagina("tarefas")
    j.selecionar_lista("hoje")
    for i in range(j.tarefas.count()):
        t = j.tarefas.item(i).data(PAPEL_TAREFA)
        if t is not None and t.titulo.startswith("Estudar para"):
            j.tarefas.setCurrentRow(i)
    app.processEvents()
    j.detalhe.rolagem.verticalScrollBar().setValue(10_000)
    app.processEvents()
    foto("25-detalhe-comentarios-e-foco.png")

    # ---- calendário em todos os modos, cartão, hábitos e busca ----
    from datetime import date as _d
    from PySide6.QtCore import QRect
    j.mostrar_pagina("calendario")
    pag = j.pagina_calendario
    for n, modo in enumerate(("mes", "semana", "dia", "ano", "agenda", "multidia", "multisemana"), start=26):
        pag.definir_modo(modo)
        foto(f"{n}-calendario-{modo}.png")
    pag.definir_modo("mes")
    cartao = pag.abrir_cartao_novo(_d.today(), None, QRect(300, 300, 100, 100))
    cartao.titulo.setText("votação das eleições")
    app.processEvents()
    cartao.grab().save(str(saida / "33-cartao-de-tarefa.png"))
    seletor = cartao.abrir_data()
    app.processEvents()
    seletor.grab().save(str(saida / "34-seletor-de-data.png"))
    seletor.close()
    cartao.close()
    j.mostrar_pagina("habitos")
    j.pagina_habitos.alternar_visao()
    foto("35-habitos-grade.png")
    j.pagina_habitos.alternar_visao()
    from norteia.ui.dialogos import DialogoHabito
    dlg = DialogoHabito(j)
    dlg.nome.setText("Meditar")
    dlg.show()
    app.processEvents()
    dlg.grab().save(str(saida / "36-criar-habito.png"))
    dlg.close()
    j.mostrar_pagina("tarefas")
    j.abrir_busca("estudar")
    app.processEvents()
    j.painel_busca.grab().save(str(saida / "37-busca-flutuante.png"))
    j.painel_busca.close()


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "capturas"))
