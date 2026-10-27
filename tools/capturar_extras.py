"""Capturas do assistente de IA, do calendário com sobreposição e das integrações (dados e provedores simulados).

Uso: python tools/capturar_extras.py <pasta_saida>

Nada aqui fala com a internet: a IA usa respostas de mentira (as mesmas dos testes) e o Google usa uma API simulada.
"""
from __future__ import annotations

import os
import random
import sys
import tempfile
from datetime import date, time, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from norteia.core import Banco, Servico  # noqa: E402
from norteia.core.arquivos_ia import Anexo  # noqa: E402
from norteia.core.google_agenda import Cofre, Google  # noqa: E402
from norteia.core.ia_provedores import CofreIA, ConfigIA  # noqa: E402
from norteia.core.models import Tarefa  # noqa: E402
from norteia.demo import popular  # noqa: E402
from norteia.ui import tema  # noqa: E402
from norteia.ui.dialogo_google import DialogoGoogle, DialogoIntegracoes, GerenteGoogle  # noqa: E402
from norteia.ui.janela import JanelaPrincipal  # noqa: E402
from norteia.ui.pagina_ia import DialogoIA, _imagem_para_png  # noqa: E402
from tests.test_google_agenda import GoogleFalso  # noqa: E402
from tests.test_ia_assistente import Chamada, IAFalsa  # noqa: E402
from tests.test_ui_ia_anexos_voz import FonteFalsa, pcm_seno  # noqa: E402


def _servico(demo: bool = False) -> Servico:
    svc = Servico(Banco(":memory:"), pasta_dados=Path(tempfile.mkdtemp()))
    svc._extras["ia"] = ConfigIA(svc.banco, CofreIA(svc.banco, usar_keyring=False))
    if demo:
        popular(svc)
    return svc


def _janela(svc: Servico, largura: int = 1280, altura: int = 800) -> JanelaPrincipal:
    j = JanelaPrincipal(svc, notificador=lambda t, x: None, prefs={}, google_em_thread=False)
    j.resize(largura, altura)
    j.show()
    j.pagina_ia.em_thread = False
    return j


def main(saida: Path) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])

    def foto(widget, nome: str) -> None:
        app.processEvents()
        widget.grab().save(str(saida / nome))

    # ---- IA: sem chave, configuração, plano, anexos e voz ----
    svc = _servico(demo=True)
    j = _janela(svc)
    j.mostrar_pagina("ia")
    j.pagina_ia.atualizar_estado()
    foto(j, "ia-sem-chave.png")

    dlg = DialogoIA(j, svc, em_thread=False)
    dlg.campo_chave.setText("chave-de-demonstracao-0000")
    dlg.salvar_chave()   # a chave do Gemini fica salva e ativa
    dlg.show()
    foto(dlg, "ia-configuracao.png")
    dlg.close()

    svc.ia.salvar_chave("claude", "chave-de-demonstracao-0000")
    svc.ia.definir_ativo("claude")
    p = j.pagina_ia
    amanha = (date.today() + timedelta(days=1)).isoformat()
    alvo = svc.salvar(Tarefa(titulo="Entregar relatório de estágio", prazo=date.today(), ordem=1))
    p.transporte = IAFalsa("claude", [
        ("", [Chamada("c1", "atualizar_tarefa", {"id": alvo.id, "data": amanha})]),
        (f"Passei \"{alvo.titulo}\" para amanhã. Confira o plano e clique em Aplicar tudo.", [])])
    j.mostrar_pagina("ia")
    p.atualizar_estado()
    p.enviar(f"Adie a tarefa \"{alvo.titulo}\" para amanhã")
    foto(j, "ia-plano-proposto.png")
    p.cartoes[0].btn_aplicar.click()
    foto(j, "ia-plano-aplicado.png")

    svc.ia.definir_ativo("gemini")          # voz só funciona com Gemini ou ChatGPT
    p.atualizar_estado()
    p.nova_conversa()
    img = QImage(300, 200, QImage.Format_RGB32)
    img.fill(QColor("#2a3a6a"))
    pintor = QPainter(img)
    pintor.setPen(QColor("white"))
    pintor.drawText(20, 100, "Horário de aulas - 2º semestre")
    pintor.end()
    p.adicionar_anexo(Anexo("horario.png", "image/png", dados=_imagem_para_png(img)))
    p.adicionar_anexo(Anexo("ementa.pdf", "application/pdf", dados=b"%PDF-1.4 demo"))
    foto(j, "ia-anexos.png")
    p.transporte = IAFalsa("gemini", [("Vi um horário de aulas. Quer que eu crie as tarefas?", [])])
    p.entrada.setPlainText("crie eventos com esse horário")
    p.enviar()

    random.seed(7)
    p.gravador.fabrica = FonteFalsa
    p.comecar_gravacao()
    fonte = FonteFalsa.instancias[-1]
    for _ in range(40):
        fonte.receber(pcm_seno(0.05, amplitude=random.choice([1500, 4000, 9000, 2500, 7000])))
        p.barra_gravacao.onda.passo()
    foto(j, "ia-voz.png")
    j.close()

    # ---- Calendário com eventos sobrepostos (estilo Google Agenda) ----
    svc = _servico()
    hoje = date.today()

    def evento(titulo, dia, hora, minutos):
        svc.salvar(Tarefa(titulo=titulo, prazo=dia, prazo_hora=time(hora), duracao_min=minutos, ordem=1))

    evento("Estágio", hoje, 8, 240)
    evento("Aula de inglês", hoje, 10, 60)
    evento("Estágio", hoje + timedelta(days=1), 14, 240)
    evento("Aula de inglês", hoje + timedelta(days=1), 14, 60)
    evento("Faculdade", hoje + timedelta(days=2), 8, 240)
    evento("Estudar", hoje + timedelta(days=2), 10, 90)
    evento("Revisar", hoje + timedelta(days=2), 10, 30)
    j = _janela(svc, 1300, 800)
    j.mostrar_pagina("calendario")
    j.pagina_calendario.definir_modo("multidia")
    foto(j, "calendario-sobreposicao.png")
    j.close()

    # ---- Integrações: Google Calendar (API simulada) ----
    svc = _servico()
    falso = GoogleFalso()
    svc._extras["google"] = Google(svc, transporte=falso, cofre=Cofre(svc.banco, usar_keyring=False))
    gerente = GerenteGoogle(svc, em_thread=False, transporte=falso)
    app.setStyleSheet(tema.qss())
    d = DialogoIntegracoes(None, lambda: None, lambda: None)
    d.show()
    foto(d, "integracoes.png")
    d.close()
    d = DialogoGoogle(None, svc, gerente)
    d.show()
    foto(d, "google-conectar.png")
    svc.google.cliente.definir_credenciais("id", "segredo")
    svc.google.cliente.guardar_login({"refresh_token": "r", "access_token": "", "expira_em": 0})
    gerente.sincronizar()
    d.caixas["Trabalho"].setChecked(True)
    d.chk_enviar.setChecked(True)
    d._atualizar()
    foto(d, "google-conectado.png")
    d.close()


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "capturas"))
