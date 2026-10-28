"""Anexos (imagem, PDF, texto) e voz no chat do assistente."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import base64
import json
import math
import struct

import pytest
from PySide6.QtGui import QColor, QImage

from norteia.core.arquivos_ia import MAX_ANEXOS, Anexo, ConversorPCM, wav_de_pcm16
from norteia.core.ia import ErroIA
from norteia.ui.pagina_ia import ChipAnexo, reduzir_imagem
from norteia.ui.voz import Gravador, OndaVoz, formatar_tempo
from tests.test_ia_assistente import IAFalsa
from tests.test_ui_ia import app, janela  # noqa: F401  (fixtures)


def png_bytes(largura=40, altura=30, cor="#3366cc") -> bytes:
    from norteia.ui.pagina_ia import _imagem_para_png
    img = QImage(largura, altura, QImage.Format_RGB32)
    img.fill(QColor(cor))
    return _imagem_para_png(img)


def pagina(janela, provedor="claude", roteiro=None):
    svc = janela.servico
    svc.ia.salvar_chave(provedor, "chave-de-teste-123456")
    svc.ia.definir_ativo(provedor)
    p = janela.pagina_ia
    p.transporte = IAFalsa("gemini" if provedor == "gemini" else "claude" if provedor == "claude" else "openai",
                           roteiro or [("Entendi.", [])])
    janela.mostrar_pagina("ia")
    p.atualizar_estado()
    return p


def pcm_seno(segundos=0.5, amplitude=8000, taxa=16000, freq=220) -> bytes:
    n = int(segundos * taxa)
    return struct.pack("<" + "h" * n, *[int(amplitude * math.sin(2 * math.pi * freq * i / taxa)) for i in range(n)])


class FonteFalsa:
    instancias = []

    def __init__(self):
        self.receber, self.aberta = None, False
        FonteFalsa.instancias.append(self)

    def abrir(self, ao_receber):
        self.receber, self.aberta = ao_receber, True

    def fechar(self):
        self.aberta = False


class FonteSemMicrofone:
    def abrir(self, ao_receber):
        raise ErroIA("Não encontrei um microfone. Conecte um e tente de novo.")

    def fechar(self):
        pass


# ---------------------------------------------------------------- anexos
def test_imagem_anexada_aparece_em_chip_e_vai_para_a_ia(janela):
    p = pagina(janela)
    p.adicionar_anexo(Anexo("tela.png", "image/png", dados=png_bytes()))
    assert len(p.anexos) == 1 and p.barra_anexos.isVisibleTo(p)
    assert len(p.barra_anexos.findChildren(ChipAnexo)) == 1
    p.entrada.setPlainText("o que tem nessa imagem?")
    p.enviar()
    corpo = json.dumps(p.transporte.pedidos[0][2])
    assert '"type": "image"' in corpo and base64.b64encode(png_bytes()).decode() in corpo
    assert p.anexos == [] and not p.barra_anexos.isVisibleTo(p)                   # chips limpos depois do envio
    assert p.corpo.findChildren(type(p.titulo), "anexoNaConversa")               # miniatura na conversa
    assert p.historico[0]["anexos"][0]["nome"] == "tela.png"


def test_so_anexo_sem_texto_pode_ser_enviado(janela):
    p = pagina(janela)
    p.adicionar_anexo(Anexo("tela.png", "image/png", dados=png_bytes()))
    p.enviar()
    assert len(p.transporte.pedidos) == 1 and p.historico[0]["texto"] == ""
    assert "Veja o anexo" in json.dumps(p.transporte.pedidos[0][2], ensure_ascii=False)


def test_arquivo_de_texto_vai_como_texto(janela, tmp_path):
    p = pagina(janela)
    f = tmp_path / "notas.txt"
    f.write_text("Reunião quinta às 14h com a diretoria", encoding="utf-8")
    assert p.adicionar_arquivos([str(f)]) == 1
    p.entrada.setPlainText("crie tarefas disso")
    p.enviar()
    corpo = json.dumps(p.transporte.pedidos[0][2], ensure_ascii=False)
    assert "Reunião quinta às 14h" in corpo and '"type": "image"' not in corpo


def test_remover_chip_e_limite_de_anexos(janela):
    p = pagina(janela)
    for i in range(MAX_ANEXOS):
        p.adicionar_anexo(Anexo(f"a{i}.png", "image/png", dados=png_bytes()))
    with pytest.raises(ErroIA, match="até 5"):
        p.adicionar_anexo(Anexo("a6.png", "image/png", dados=png_bytes()))
    chip = p.barra_anexos.findChildren(ChipAnexo)[0]
    chip.btn_remover.click()
    assert len(p.anexos) == MAX_ANEXOS - 1
    p.remover_anexo(p.anexos[0]); p.remover_anexo(p.anexos[0]); p.remover_anexo(p.anexos[0]); p.remover_anexo(p.anexos[0])
    assert p.anexos == [] and not p.barra_anexos.isVisibleTo(p)


def test_arquivo_nao_suportado_mostra_mensagem(janela, tmp_path):
    p = pagina(janela)
    f = tmp_path / "video.mp4"
    f.write_bytes(b"\x00\x01")
    assert p.adicionar_arquivos([str(f)]) == 0
    assert "Ainda não sei ler" in p.status.text() and p.anexos == []


def test_deepseek_aceita_imagem(janela):
    p = pagina(janela, "deepseek")
    p.adicionar_anexo(Anexo("a.png", "image/png", dados=png_bytes()))
    assert [a.nome for a in p.anexos] == ["a.png"]


def test_ia_que_nao_le_imagem_recusa_com_aviso(janela, monkeypatch):
    from dataclasses import replace
    import norteia.core.ia_provedores as provs
    monkeypatch.setitem(provs.PROVEDORES, "deepseek", replace(provs.PROVEDORES["deepseek"], le_imagem=False))
    p = pagina(janela, "deepseek")
    with pytest.raises(ErroIA, match="não lê imagens"):
        p.adicionar_anexo(Anexo("a.png", "image/png", dados=png_bytes()))


def test_trocar_para_ia_sem_imagem_barra_o_envio_com_anexo(janela, monkeypatch):
    from dataclasses import replace
    import norteia.core.ia_provedores as provs
    monkeypatch.setitem(provs.PROVEDORES, "deepseek", replace(provs.PROVEDORES["deepseek"], le_imagem=False))
    p = pagina(janela)
    p.adicionar_anexo(Anexo("a.png", "image/png", dados=png_bytes()))
    janela.servico.ia.salvar_chave("deepseek", "chave-deepseek-123")
    janela.servico.ia.definir_ativo("deepseek")
    p.entrada.setPlainText("olhe")
    p.enviar()
    assert "não lê imagens" in p.status.text() and p.transporte.pedidos == [] and len(p.anexos) == 1


def test_colar_imagem_vira_anexo(janela):
    p = pagina(janela)
    img = QImage(30, 20, QImage.Format_RGB32)
    img.fill(QColor("#aa3333"))
    p.entrada.colou.emit(img)
    p.entrada.colou.emit(img)
    assert [a.nome for a in p.anexos] == ["imagem-colada-1.png", "imagem-colada-2.png"]


def test_imagem_muito_grande_e_reduzida():
    grande = Anexo("foto.png", "image/png", dados=png_bytes(4000, 1000))
    menor = reduzir_imagem(grande)
    img = QImage.fromData(menor.dados)
    assert max(img.width(), img.height()) == 2048 and menor.mime == "image/png"
    pequena = Anexo("p.png", "image/png", dados=png_bytes())
    assert reduzir_imagem(pequena) is pequena


def test_conversa_reaberta_mostra_nome_do_anexo_sem_os_bytes(janela):
    p = pagina(janela)
    p.adicionar_anexo(Anexo("tela.png", "image/png", dados=png_bytes()))
    p.entrada.setPlainText("veja")
    p.enviar()
    cid = p.conversa_id
    p.nova_conversa()
    p.abrir_conversa(cid)
    assert "b64" not in json.dumps(p.historico[0]["anexos"])
    rotulos = [w.text() for w in p.corpo.findChildren(type(p.titulo), "anexoNaConversa")]
    assert rotulos == ["Imagem: tela.png"]


# ---------------------------------------------------------------- voz
def test_gravar_voz_mostra_onda_e_transcreve_para_a_caixa(janela):
    FonteFalsa.instancias.clear()
    p = pagina(janela, "gemini", [("reunião com o Pedro amanhã às 10h", [])])
    p.gravador.fabrica = FonteFalsa
    assert p.comecar_gravacao()
    assert p.barra_gravacao.isVisibleTo(p) and not p.linha_entrada.isVisibleTo(p)
    fonte = FonteFalsa.instancias[-1]
    fonte.receber(pcm_seno(0.5))
    assert p.barra_gravacao.rotulo.text() == "0:00"
    p.barra_gravacao.onda.passo()
    assert max(p.barra_gravacao.onda.valores) > 0.2
    p.terminar_gravacao()
    assert not fonte.aberta and p.linha_entrada.isVisibleTo(p) and not p.barra_gravacao.isVisibleTo(p)
    assert p.entrada.toPlainText() == "reunião com o Pedro amanhã às 10h"
    assert "Revise" in p.status.text() and not p.transcrevendo and p.btn_voz.isEnabled()
    corpo = json.dumps(p.transporte.pedidos[0][2])
    assert "audio/wav" in corpo and base64.b64encode(wav_de_pcm16(pcm_seno(0.5))).decode() in corpo
    assert p.historico == []                                    # a transcrição não é enviada sozinha


def test_voz_com_ia_que_nao_transcreve_avisa_sem_gravar(janela):
    FonteFalsa.instancias.clear()
    p = pagina(janela, "claude")
    p.gravador.fabrica = FonteFalsa
    assert not p.comecar_gravacao()
    assert "não transcreve voz" in p.status.text() and FonteFalsa.instancias == []


def test_sem_microfone_mostra_mensagem_amigavel(janela):
    p = pagina(janela, "gemini")
    p.gravador.fabrica = FonteSemMicrofone
    assert not p.comecar_gravacao()
    assert "microfone" in p.status.text() and p.linha_entrada.isVisibleTo(p) and not p.gravador.gravando


def test_cancelar_gravacao_nao_envia_nada(janela):
    FonteFalsa.instancias.clear()
    p = pagina(janela, "gemini")
    p.gravador.fabrica = FonteFalsa
    p.comecar_gravacao()
    FonteFalsa.instancias[-1].receber(pcm_seno(0.3))
    p.barra_gravacao.btn_cancelar.click()
    assert not p.gravador.gravando and p.transporte.pedidos == [] and p.linha_entrada.isVisibleTo(p)
    assert p.entrada.toPlainText() == ""


def test_gravacao_curtissima_e_ignorada(janela):
    FonteFalsa.instancias.clear()
    p = pagina(janela, "gemini")
    p.gravador.fabrica = FonteFalsa
    p.comecar_gravacao()
    p.terminar_gravacao()
    assert "Não ouvi nada" in p.status.text() and p.transporte.pedidos == []


def test_silencio_total_sugere_conferir_privacidade_do_windows(janela):
    FonteFalsa.instancias.clear()
    p = pagina(janela, "gemini")
    p.gravador.fabrica = FonteFalsa
    p.comecar_gravacao()
    p.gravador._sem_som()
    assert "Privacidade" in p.status.text() and not p.gravador.gravando and p.linha_entrada.isVisibleTo(p)


def test_limite_de_tempo_encerra_e_transcreve(janela):
    FonteFalsa.instancias.clear()
    p = pagina(janela, "gemini", [("texto falado", [])])
    p.gravador.fabrica = FonteFalsa
    p.gravador.limite_segundos = 1
    p.comecar_gravacao()
    FonteFalsa.instancias[-1].receber(pcm_seno(1.2))
    assert not p.gravador.gravando and p.entrada.toPlainText() == "texto falado"


def test_erro_na_transcricao_aparece_e_destrava_o_botao(janela):
    FonteFalsa.instancias.clear()
    p = pagina(janela, "gemini")
    p.gravador.fabrica = FonteFalsa

    def falha(*a, **k):
        raise ErroIA("Limite de uso da IA atingido.")

    p.transporte = falha
    p.comecar_gravacao()
    FonteFalsa.instancias[-1].receber(pcm_seno(0.5))
    p.terminar_gravacao()
    assert "Limite" in p.status.text() and p.btn_voz.isEnabled() and not p.transcrevendo


def test_voz_com_chatgpt_manda_arquivo_para_whisper(janela):
    FonteFalsa.instancias.clear()
    p = pagina(janela, "openai")
    p.gravador.fabrica = FonteFalsa
    chamadas = []
    p.transporte_arquivo = lambda url, cab, campos, arq: (chamadas.append((url, campos, arq[1])) or {"text": "oi pessoal"})
    p.comecar_gravacao()
    FonteFalsa.instancias[-1].receber(pcm_seno(0.5))
    p.terminar_gravacao()
    assert chamadas[0][0].endswith("/audio/transcriptions") and chamadas[0][1]["model"] == "gpt-transcribe"
    assert p.entrada.toPlainText() == "oi pessoal"


def test_voz_com_groq_enquanto_o_chat_usa_claude(janela):
    FonteFalsa.instancias.clear()
    p = pagina(janela, "claude")
    janela.servico.ia.salvar_chave("groq", "chave-groq-123456")
    janela.servico.ia.definir_voz("groq")
    p.gravador.fabrica = FonteFalsa
    chamadas = []
    p.transporte_arquivo = lambda url, cab, campos, arq: (chamadas.append((url, campos)) or {"text": "marcar dentista"})
    assert p.comecar_gravacao()
    FonteFalsa.instancias[-1].receber(pcm_seno(0.5))
    p.terminar_gravacao()
    assert chamadas[0][0].startswith("https://api.groq.com/") and chamadas[0][1]["language"] == "pt"
    assert p.entrada.toPlainText() == "marcar dentista" and p.transporte.pedidos == []   # o chat não foi chamado


def test_onda_sobe_com_voz_alta_e_desce_no_silencio(app):
    o = OndaVoz()
    o.resize(200, 40)
    for _ in range(6):
        o.definir_nivel(0.6)
        o.passo()
    alto = o.valores[-1]
    for _ in range(12):
        o.passo()
    assert alto > 0.5 and o.valores[-1] < 0.05
    assert len(o.valores) == OndaVoz.BARRAS and o.width() > 0
    o.grab()                                    # desenha sem erro


def test_formatar_tempo():
    assert formatar_tempo(0) == "0:00" and formatar_tempo(65.9) == "1:05"


# ---------------------------------------------------------------- conversor de áudio
def test_conversor_nao_mexe_em_16k_mono_int16():
    c = ConversorPCM(16000, 1, "int16")
    d = pcm_seno(0.1)
    assert c.converter(d) == d


def test_conversor_48k_estereo_float_vira_16k_mono_int16():
    c = ConversorPCM(48000, 2, "float")
    n = 4800                                          # 0,1 s
    import array
    v = array.array("f")
    for i in range(n):
        x = 0.5 * math.sin(2 * math.pi * 200 * i / 48000)
        v.extend([x, x])
    saida = c.converter(v.tobytes())
    amostras = struct.unpack("<" + "h" * (len(saida) // 2), saida)
    assert len(amostras) == 1600 and max(amostras) > 14000 and min(amostras) < -14000


def test_conversor_junta_blocos_quebrados_no_meio_de_um_quadro():
    c = ConversorPCM(32000, 1, "int16")
    d = struct.pack("<hhhh", 100, 200, 300, 400)
    saida = c.converter(d[:3]) + c.converter(d[3:])
    assert struct.unpack("<hh", saida) == (100, 300)


# ---------------------------------------------------------------- microfone de verdade (Qt) e tamanho da janela
def test_janela_pode_ser_reduzida_em_todas_as_paginas(janela):
    janela.resize(1200, 800)
    assert janela.minimumWidth() <= 900 and janela.minimumHeight() <= 560
    for chave in ("tarefas", "calendario", "ia", "matriz", "linha-tempo", "habitos", "foco"):
        try:
            janela.mostrar_pagina(chave)
        except Exception:  # noqa: BLE001 - nome de página que não existe nesta versão
            continue
        janela.resize(1000, 640)
        assert janela.width() <= 1000, chave


def test_fonte_qt_usa_os_nomes_certos_da_api_do_qt(monkeypatch):
    """O microfone não existe no ambiente de teste, então troco o dispositivo por um falso, mas com as enums reais."""
    from PySide6 import QtMultimedia as mm
    from PySide6.QtCore import QObject, Signal
    from norteia.ui.voz import FonteQt

    class Io(QObject):
        readyRead = Signal()

        def __init__(self):
            super().__init__()
            self.fila = b""

        def readAll(self):
            d, self.fila = self.fila, b""
            return d

    io = Io()

    class Dispositivo:
        def isNull(self): return False
        def isFormatSupported(self, f): return False
        def preferredFormat(self):
            f = mm.QAudioFormat()
            f.setSampleRate(48000); f.setChannelCount(2); f.setSampleFormat(mm.QAudioFormat.Float)
            return f

    class Fonte:
        def __init__(self, dev, fmt): self.fmt = fmt
        def start(self): return io
        def error(self): return mm.QtAudio.Error.NoError
        def stop(self): pass

    monkeypatch.setattr(mm.QMediaDevices, "defaultAudioInput", staticmethod(lambda: Dispositivo()))
    monkeypatch.setattr(mm, "QAudioSource", Fonte)
    recebido = []
    f = FonteQt()
    f.abrir(recebido.append)
    import array
    v = array.array("f", [0.5, 0.5] * 4800)
    io.fila = v.tobytes()
    io.readyRead.emit()
    assert len(recebido) == 1 and len(recebido[0]) == 1600 * 2         # 0,1 s a 16 kHz, 16 bits
    f.fechar()


def test_fonte_qt_erro_do_microfone_vira_mensagem(monkeypatch):
    from PySide6 import QtMultimedia as mm
    from norteia.ui.voz import FonteQt

    class Dispositivo:
        def isNull(self): return False
        def isFormatSupported(self, f): return True

    class Fonte:
        def __init__(self, dev, fmt): pass
        def start(self): return None
        def error(self): return mm.QtAudio.Error.OpenError
        def stop(self): pass

    monkeypatch.setattr(mm.QMediaDevices, "defaultAudioInput", staticmethod(lambda: Dispositivo()))
    monkeypatch.setattr(mm, "QAudioSource", Fonte)
    with pytest.raises(ErroIA, match="Privacidade"):
        FonteQt().abrir(lambda b: None)


def test_falha_inesperada_ao_gravar_nao_derruba_a_tela(janela):
    p = pagina(janela, "gemini")

    class Quebrada:
        def abrir(self, cb):
            raise RuntimeError("driver de áudio quebrou")

        def fechar(self):
            pass

    p.gravador.fabrica = Quebrada
    assert not p.comecar_gravacao()
    assert "driver de áudio quebrou" in p.status.text() and p.linha_entrada.isVisibleTo(p)
