"""Assistente de IA: provedores, chave no cofre, ferramentas, plano com confirmação e desfazer."""
import json
from datetime import date, time, timedelta

import pytest

from norteia.core import Banco, Servico
from norteia.core import assistente as ass
from norteia.core import ia_provedores as prov
from norteia.core.exportacao import exportar_json
from norteia.core.ia import ErroIA
from norteia.core.ia_provedores import Chamada, ConfigIA, CofreIA, Pedido
from norteia.core.models import Prioridade, Tarefa

HOJE = date(2026, 10, 26)       # segunda-feira


# ---------- IA falsa: devolve respostas prontas no formato nativo de cada provedor ----------
def nativo(formato, texto="", chamadas=()):
    if formato == "gemini":
        partes = ([{"text": texto}] if texto else []) + [{"functionCall": {"name": c.nome, "args": c.args}} for c in chamadas]
        return {"candidates": [{"content": {"parts": partes}}]}
    if formato == "claude":
        blocos = ([{"type": "text", "text": texto}] if texto else []) + [
            {"type": "tool_use", "id": c.id, "name": c.nome, "input": c.args} for c in chamadas]
        return {"content": blocos}
    msg = {"content": texto or None}
    if chamadas:
        msg["tool_calls"] = [{"id": c.id, "type": "function",
                              "function": {"name": c.nome, "arguments": json.dumps(c.args)}} for c in chamadas]
    return {"choices": [{"message": msg}]}


class IAFalsa:
    def __init__(self, formato, roteiro):
        self.formato, self.roteiro, self.pedidos = formato, list(roteiro), []

    def __call__(self, url, cabecalhos, corpo, timeout=0):
        self.pedidos.append((url, cabecalhos, json.loads(corpo)))
        texto, chamadas = self.roteiro.pop(0)
        return nativo(self.formato, texto, chamadas)


def servico(tmp_path=None):
    return Servico(Banco(":memory:"))


def config(svc):
    c = ConfigIA(svc.banco, CofreIA(svc.banco, usar_keyring=False))
    svc._extras["ia"] = c
    return c


def pedido(provedor="gemini", **kw):
    return Pedido(provedor, prov.PROVEDORES[provedor].modelo_padrao, "chave-secreta-123", **kw)


def tarefa(svc, titulo, dia=None, h=None, **kw):
    t = Tarefa(titulo=titulo, prazo=dia, prazo_hora=h, ordem=svc.banco.proxima_ordem(), **kw)
    return svc.salvar(t)


# ---------- provedores ----------
@pytest.mark.parametrize("nome,fmt", [("gemini", "gemini"), ("claude", "claude"), ("openai", "openai"),
                                      ("deepseek", "openai")])
def test_cada_provedor_monta_o_pedido_e_le_a_resposta(nome, fmt):
    ia = IAFalsa(fmt, [("oi!", [])])
    r = prov.conversar(pedido(nome), "sistema", [{"papel": "usuario", "texto": "olá"}], ass.FERRAMENTAS, ia)
    assert r.texto == "oi!" and not r.chamadas
    url, cab, corpo = ia.pedidos[0]
    assert url.startswith(prov.PROVEDORES[nome].base)
    assert "chave-secreta-123" not in url                         # a chave nunca vai na URL
    assert "chave-secreta-123" in json.dumps(cab)
    assert "sistema" in json.dumps(corpo) and "listar_tarefas" in json.dumps(corpo)


@pytest.mark.parametrize("fmt,nome", [("gemini", "gemini"), ("claude", "claude"), ("openai", "deepseek")])
def test_chamada_de_ferramenta_e_resultado_voltam_no_formato_certo(fmt, nome):
    c = Chamada("c1", "listar_tarefas", {"filtro": "hoje"})
    ia = IAFalsa(fmt, [("", [c]), ("pronto", [])])
    hist = [{"papel": "usuario", "texto": "x"}]
    r = prov.conversar(pedido(nome), "s", hist, ass.FERRAMENTAS, ia)
    assert r.chamadas == [Chamada(r.chamadas[0].id, "listar_tarefas", {"filtro": "hoje"})]
    hist += [{"papel": "assistente", "texto": "", "chamadas": [{"id": r.chamadas[0].id, "nome": "listar_tarefas",
                                                                 "args": {"filtro": "hoje"}}]},
             {"papel": "ferramenta", "resultados": [{"id": r.chamadas[0].id, "nome": "listar_tarefas",
                                                     "conteudo": "{\"total\": 0}"}]}]
    assert prov.conversar(pedido(nome), "s", hist, ass.FERRAMENTAS, ia).texto == "pronto"
    assert "total" in json.dumps(ia.pedidos[1][2], ensure_ascii=False)


def test_gemini_reenvia_as_partes_originais_da_chamada():
    bruto = [{"functionCall": {"name": "ver_listas", "args": {}}, "thoughtSignature": "abc"}]
    hist = [{"papel": "usuario", "texto": "x"},
            {"papel": "assistente", "texto": "", "chamadas": [{"id": "g0", "nome": "ver_listas", "args": {}}],
             "bruto_gemini": bruto}]
    _, _, corpo = prov._pedido_gemini(prov.PROVEDORES["gemini"], "m", "k", "s", hist, [])
    assert corpo["contents"][1]["parts"] == bruto


def test_erros_de_http_viram_mensagens_claras():
    assert "chave" in prov._mensagem_http(401, "")
    assert "Limite" in prov._mensagem_http(429, "")
    assert "modelo" in prov._mensagem_http(404, "")
    assert "saldo" in prov._mensagem_http(402, "")


def test_sem_chave_nao_chama_a_rede():
    p = Pedido("claude", "m", "")
    with pytest.raises(ErroIA, match="Falta a chave"):
        prov.conversar(p, "s", [{"papel": "usuario", "texto": "x"}], None, lambda *a, **k: pytest.fail("rede"))


def test_testar_conexao_devolve_o_texto():
    assert prov.testar_conexao(pedido("openai"), IAFalsa("openai", [("ok", [])])) == "ok"


# ---------- chave ----------
def test_chave_so_aparece_mascarada_e_nao_vaza_em_backup_nem_repr():
    svc = servico()
    c = config(svc)
    assert c.mascara("claude") == "sem chave" and not c.tem_chave("claude")
    c.salvar_chave("claude", "  sk-ant-segredo-ABCD \n")
    assert c.tem_chave("claude")
    assert c.mascara("claude").endswith("ABCD") and "segredo" not in c.mascara("claude")
    assert c.chave_para_uso("claude") == "sk-ant-segredo-ABCD"           # espaços de colagem saem
    assert "segredo" not in exportar_json(svc)                           # fora do backup
    assert "segredo" not in repr(c.pedido()) and "segredo" not in str(c.pedido())
    c.apagar_chave("claude")
    assert not c.tem_chave("claude") and c.mascara("claude") == "sem chave"
    assert c.chave_para_uso("claude") == ""


def test_chave_curta_e_provedor_invalido_sao_recusados():
    c = config(servico())
    with pytest.raises(ErroIA):
        c.salvar_chave("gemini", "abc")
    with pytest.raises(ValueError):
        c.salvar_chave("xpto", "a" * 20)
    with pytest.raises(ValueError):
        c.definir_ativo("xpto")


def test_provedor_padrao_modelo_e_preferencias():
    c = config(servico())
    assert c.ativo == "gemini" and c.modelo() == prov.PROVEDORES["gemini"].modelo_padrao
    c.definir_ativo("deepseek")
    c.definir_modelo("deepseek", " meu-modelo ")
    assert c.modelo() == "meu-modelo"
    c.definir_modelo("deepseek", "")
    assert c.modelo() == "deepseek-chat"
    c.adicionar_preferencia("não marcar nada antes das 8h")
    c.adicionar_preferencia("não marcar nada antes das 8h")
    assert c.preferencias == ["não marcar nada antes das 8h"]


# ---------- assistente ----------
def novo(svc, roteiro, fmt="claude", **kw):
    ia = IAFalsa(fmt, roteiro)
    return ass.Assistente(svc, pedido("claude", **kw), ia, hoje=HOJE), ia


def test_leitura_roda_na_hora_e_o_resultado_chega_na_ia():
    svc = servico()
    tarefa(svc, "Estudar SAD", HOJE, time(14, 0), notas="capítulo 3")
    a, ia = novo(svc, [("", [Chamada("c1", "listar_tarefas", {"filtro": "hoje"})]), ("Você tem 1 tarefa.", [])])
    t = a.turno([], "o que tenho hoje?")
    assert t.texto == "Você tem 1 tarefa." and not t.plano
    resultado = json.dumps(ia.pedidos[1][2], ensure_ascii=False)
    assert "Estudar SAD" in resultado and "capítulo 3" in resultado
    assert [m["papel"] for m in t.historico] == ["usuario", "assistente", "ferramenta", "assistente"]
    assert "2026-10-26" in ia.pedidos[0][2]["system"] and "segunda-feira" in ia.pedidos[0][2]["system"]


def test_notas_nao_vao_quando_a_pessoa_desliga():
    svc = servico()
    tarefa(svc, "Estudar", HOJE, notas="segredo do cliente")
    a, ia = novo(svc, [("", [Chamada("c1", "listar_tarefas", {"filtro": "todas"})]), ("ok", [])], enviar_notas=False)
    a.turno([], "x")
    assert "segredo do cliente" not in json.dumps(ia.pedidos)


def test_escrita_so_propoe_e_nada_muda_antes_de_aplicar():
    svc = servico()
    t = tarefa(svc, "Relatório", HOJE)
    roteiro = [("", [Chamada("c1", "atualizar_tarefa", {"id": t.id, "data": "2026-10-28", "hora": "09:00"}),
                     Chamada("c2", "criar_tarefa", {"titulo": "Revisar", "data": "2026-10-27", "prioridade": "alta"})]),
               ("Proposta pronta, revise.", [])]
    a, _ = novo(svc, roteiro)
    turno = a.turno([], "reagende")
    assert len(turno.plano.acoes) == 2 and "Revisar" in turno.plano.acoes[1].resumo
    assert svc.banco.obter_tarefa(t.id).prazo == HOJE and len(svc.buscar("Revisar")) == 0
    lote = ass.aplicar_plano(svc, turno.plano)
    novo_t = svc.banco.obter_tarefa(t.id)
    assert novo_t.prazo == date(2026, 10, 28) and novo_t.prazo_hora == time(9, 0)
    criada = svc.buscar("Revisar")[0]
    assert criada.prioridade == Prioridade.ALTA and criada.prazo == date(2026, 10, 27)
    assert lote.total == 2 and not lote.erros
    ass.desfazer_lote(svc, lote)
    assert svc.banco.obter_tarefa(t.id).prazo == HOJE and svc.banco.obter_tarefa(t.id).prazo_hora is None
    assert svc.buscar("Revisar") == []
    assert lote.desfeito


def test_concluir_apagar_lista_e_preferencia_com_desfazer():
    svc = servico()
    c = config(svc)
    t1, t2 = tarefa(svc, "A", HOJE), tarefa(svc, "B", HOJE)
    plano = ass.Plano([
        ass.Acao("concluir_tarefa", {"id": t1.id}, "Concluir A"),
        ass.Acao("apagar_tarefa", {"id": t2.id}, "Apagar B"),
        ass.Acao("criar_lista", {"nome": "Faculdade"}, "Criar lista"),
        ass.Acao("criar_tarefa", {"titulo": "Prova", "lista": "Faculdade", "data": "2026-11-03"}, "Criar Prova"),
        ass.Acao("guardar_preferencia", {"texto": "sábado é folga"}, "Lembrar"),
    ])
    lote = ass.aplicar_plano(svc, plano, c)
    assert not lote.erros and lote.total == 5
    assert svc.banco.obter_tarefa(t1.id).concluida and svc.banco.obter_tarefa(t2.id).apagada_em is not None
    prova = svc.buscar("Prova")[0]
    assert svc.banco.obter_projeto(prova.projeto_id).nome == "Faculdade"
    assert c.preferencias == ["sábado é folga"]
    ass.desfazer_lote(svc, lote, c)
    assert not svc.banco.obter_tarefa(t1.id).concluida and svc.banco.obter_tarefa(t2.id).apagada_em is None
    assert svc.buscar("Prova") == [] and not [p for p in svc.banco.listar_projetos() if p.nome == "Faculdade"]
    assert c.preferencias == []


def test_ferramenta_com_dado_ruim_vira_erro_para_a_ia_nao_excecao():
    svc = servico()
    roteiro = [("", [Chamada("c1", "atualizar_tarefa", {"id": 999, "titulo": "x"}),
                     Chamada("c2", "criar_tarefa", {"titulo": "Y", "data": "amanhã"}),
                     Chamada("c3", "criar_tarefa", {"titulo": "Z", "lista": "Inexistente"}),
                     Chamada("c4", "ferramenta_que_nao_existe", {})]),
               ("Não consegui.", [])]
    a, ia = novo(svc, roteiro)
    t = a.turno([], "x")
    assert not t.plano
    erros = json.dumps(ia.pedidos[1][2], ensure_ascii=False)
    assert erros.count("erro:") == 4 and "não existe tarefa" in erros and "AAAA-MM-DD" in erros


def test_lista_criada_no_mesmo_plano_vale_para_tarefa_nova():
    svc = servico()
    roteiro = [("", [Chamada("c1", "criar_lista", {"nome": "Estudos"}),
                     Chamada("c2", "criar_tarefa", {"titulo": "Ler", "lista": "Estudos"})]), ("ok", [])]
    a, _ = novo(svc, roteiro)
    assert len(a.turno([], "x").plano.acoes) == 2


def test_agenda_mostra_tarefas_e_limita_o_periodo():
    svc = servico()
    tarefa(svc, "Aula", HOJE, time(10, 0), duracao_min=90)
    a, ia = novo(svc, [("", [Chamada("c1", "ver_agenda", {"inicio": "2026-10-26", "fim": "2027-12-31"})]), ("ok", [])])
    a.turno([], "x")
    dado = json.dumps(ia.pedidos[1][2], ensure_ascii=False)
    assert "Aula" in dado and "10:00" in dado and "11:30" in dado


def test_estatisticas_e_listas_respondem():
    svc = servico()
    t = tarefa(svc, "Feita", HOJE)
    svc.alternar_conclusao(t.id)
    a, _ = novo(svc, [])
    est = a._ler_ver_estatisticas()
    assert est["concluidas_na_semana"] >= 0 and "conclusoes_por_hora_60d" in est
    assert a._ler_ver_listas()["listas"] == []


def test_para_de_rodar_em_circulos():
    svc = servico()
    loop = [("", [Chamada("c", "ver_listas", {})])] * ass.MAX_PASSOS
    a, _ = novo(svc, loop)
    t = a.turno([], "x")
    assert "Parei" in t.texto


def test_conversas_guardam_e_carregam():
    svc = servico()
    cv = svc.conversas_ia
    hist = [{"papel": "usuario", "texto": "planeja minha semana"}, {"papel": "assistente", "texto": "claro", "chamadas": []}]
    cid = cv.salvar(None, hist)
    assert cv.listar()[0]["titulo"] == "planeja minha semana"
    assert cv.carregar(cid) == hist
    cv.salvar(cid, hist + [{"papel": "usuario", "texto": "mais"}])
    assert len(cv.carregar(cid)) == 3
    cv.apagar(cid)
    assert cv.listar() == []


def test_turno_em_arquivo_usa_conexao_propria(tmp_path):
    caminho = str(tmp_path / "t.db")
    svc = Servico(Banco(caminho))
    tarefa(svc, "Do arquivo", HOJE)
    ia = IAFalsa("claude", [("", [Chamada("c1", "buscar_tarefas", {"texto": "arquivo"})]), ("achei", [])])
    t = ass.turno_em_arquivo(caminho, None, pedido("claude"), [], "x", ia)
    assert t.texto == "achei" and "Do arquivo" in json.dumps(ia.pedidos[1][2], ensure_ascii=False)


# ---------- sobrecarga passageira do provedor ----------
def _falha(codigo):
    return prov.ErroHTTP(prov._mensagem_http(codigo, ""), codigo)


def test_erro_503_tenta_de_novo_e_funciona():
    respostas = [_falha(503), _falha(503), nativo("gemini", "oi de novo")]
    chamadas, pausas = [], []

    def transporte(url, cab, corpo):
        chamadas.append(1)
        r = respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    r = prov.conversar(pedido("gemini"), "s", [{"papel": "usuario", "texto": "x"}], None, transporte, pausas.append)
    assert r.texto == "oi de novo" and len(chamadas) == 3 and pausas == [2.0, 5.0]


def test_503_persistente_vira_mensagem_clara_depois_de_3_tentativas():
    chamadas = []

    def transporte(url, cab, corpo):
        chamadas.append(1)
        raise _falha(503)

    with pytest.raises(ErroIA, match="sobrecarregado"):
        prov.conversar(pedido("gemini"), "s", [{"papel": "usuario", "texto": "x"}], None, transporte, lambda s: None)
    assert len(chamadas) == 3


def test_chave_recusada_nao_tenta_de_novo():
    chamadas = []

    def transporte(url, cab, corpo):
        chamadas.append(1)
        raise _falha(401)

    with pytest.raises(ErroIA, match="chave"):
        prov.conversar(pedido("gemini"), "s", [{"papel": "usuario", "texto": "x"}], None, transporte,
                       lambda s: pytest.fail("não deveria esperar"))
    assert len(chamadas) == 1


# ---------- anexos e voz ----------
import base64  # noqa: E402

from norteia.core import arquivos_ia as arq  # noqa: E402


def png_minimo():
    return base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def test_carregar_arquivos_por_tipo_e_limites():
    img = arq.carregar_bytes("grade.PNG", png_minimo())
    assert img.tipo == "imagem" and img.mime == "image/png"
    txt = arq.carregar_bytes("lista.txt", "compras: pão, café".encode("utf-8"))
    assert txt.tipo == "texto" and "café" in txt.texto
    assert arq.carregar_bytes("antigo.csv", "ação;dia\n".encode("cp1252")).texto.startswith("ação")
    assert arq.carregar_bytes("x.pdf", b"%PDF-1.4 ...").tipo == "pdf"
    with pytest.raises(ErroIA, match="Ainda não sei"):
        arq.carregar_bytes("musica.mp3", b"123")
    with pytest.raises(ErroIA, match="grande demais"):
        arq.carregar_bytes("enorme.png", b"0" * (arq.LIMITE_IMAGEM + 1))
    longo = arq.carregar_bytes("longo.txt", ("a" * (arq.LIMITE_TEXTO_CARACTERES + 500)).encode())
    assert "cortado" in longo.texto


def test_docx_vira_texto():
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w:document><w:p><w:r><w:t>Prova dia 12 &amp; 14</w:t></w:r></w:p></w:document>")
    a = arq.carregar_bytes("cronograma.docx", buf.getvalue())
    assert a.tipo == "texto" and "Prova dia 12 & 14" in a.texto


@pytest.mark.parametrize("nome,fmt", [("gemini", "gemini"), ("claude", "claude"), ("openai", "openai")])
def test_imagem_e_pdf_vao_no_formato_de_cada_provedor(nome, fmt):
    anexos = prov.preparar_anexos(nome, [arq.carregar_bytes("grade.png", png_minimo()),
                                          arq.carregar_bytes("calendario.pdf", b"%PDF-1.4 x"),
                                          arq.carregar_bytes("nota.txt", b"levar caderno")])
    ia = IAFalsa(fmt, [("li tudo", [])])
    r = prov.conversar(pedido(nome), "s", [{"papel": "usuario", "texto": "leia", "anexos": anexos}], None, ia)
    assert r.texto == "li tudo"
    corpo = json.dumps(ia.pedidos[0][2])
    assert base64.b64encode(png_minimo()).decode() in corpo          # a imagem foi
    assert "levar caderno" in corpo                                  # o texto foi como texto
    if fmt == "gemini":
        assert "inlineData" in corpo and "application/pdf" in corpo
    elif fmt == "claude":
        assert '"type": "image"' in corpo and '"type": "document"' in corpo
    else:
        assert "image_url" in corpo and '"type": "file"' in corpo


def test_deepseek_nao_le_imagem_mas_le_pdf_como_texto(monkeypatch):
    with pytest.raises(ErroIA, match="não lê imagens"):
        prov.preparar_anexos("deepseek", [arq.carregar_bytes("a.png", png_minimo())])
    monkeypatch.setattr(prov, "texto_do_pdf", lambda dados: "texto do pdf extraído")
    a = prov.preparar_anexos("deepseek", [arq.carregar_bytes("c.pdf", b"%PDF")])
    assert a[0]["tipo"] == "texto" and "extraído" in a[0]["texto"]


def test_pdf_sem_leitor_local_explica(monkeypatch):
    import builtins
    real = builtins.__import__

    def sem_pypdf(nome, *a, **k):
        if nome == "pypdf":
            raise ImportError
        return real(nome, *a, **k)

    monkeypatch.setattr(builtins, "__import__", sem_pypdf)
    with pytest.raises(ErroIA, match="pypdf"):
        arq.texto_do_pdf(b"%PDF")


def test_assistente_manda_anexos_e_conversa_salva_sem_os_dados():
    svc = servico()
    anexos = prov.preparar_anexos("claude", [arq.carregar_bytes("grade.png", png_minimo()),
                                              arq.carregar_bytes("nota.txt", b"sala 12")])
    a, ia = novo(svc, [("Entendi a grade.", [])])
    t = a.turno([], "crie as aulas", anexos)
    assert base64.b64encode(png_minimo()).decode() in json.dumps(ia.pedidos[0][2])
    assert "anexos" in t.historico[0]
    cid = svc.conversas_ia.salvar(None, t.historico)
    guardado = svc.conversas_ia.carregar(cid)
    assert "b64" not in json.dumps(guardado) and guardado[0]["anexos"][0]["nome"] == "grade.png"
    assert guardado[0]["anexos"][1]["texto"] == "sala 12"
    assert [m["papel"] for m in guardado] == ["usuario", "assistente"]


def test_conversa_guardada_nao_leva_chamadas_de_ferramenta():
    svc = servico()
    hist = [{"papel": "usuario", "texto": "x"},
            {"papel": "assistente", "texto": "", "chamadas": [{"id": "1", "nome": "ver_listas", "args": {}}]},
            {"papel": "ferramenta", "resultados": []},
            {"papel": "assistente", "texto": "pronto", "chamadas": []}]
    cid = svc.conversas_ia.salvar(None, hist)
    assert [m["papel"] for m in svc.conversas_ia.carregar(cid)] == ["usuario", "assistente"]


def test_wav_e_nivel_do_audio():
    import struct
    pcm = struct.pack("<" + "h" * 4, 0, 10000, -10000, 0)
    wav = arq.wav_de_pcm16(pcm)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE" and wav.endswith(pcm) and len(wav) == 44 + 8
    assert arq.nivel_do_pcm16(b"\x00" * 100) == 0.0
    assert 0.3 < arq.nivel_do_pcm16(pcm) <= 1.0
    assert arq.nivel_do_pcm16(b"") == 0.0


def test_transcricao_com_gemini_manda_o_audio():
    ia = IAFalsa("gemini", [("  marcar dentista amanhã às 9  ", [])])
    texto = prov.transcrever(pedido("gemini"), b"RIFFxxxx", ia)
    assert texto == "marcar dentista amanhã às 9"
    corpo = json.dumps(ia.pedidos[0][2])
    assert "audio/wav" in corpo and base64.b64encode(b"RIFFxxxx").decode() in corpo and "Transcreva" in corpo


def test_transcricao_com_chatgpt_usa_o_envio_de_arquivo():
    vistos = {}

    def envio(url, cab, campos, arquivo):
        vistos.update(url=url, cab=cab, campos=campos, arquivo=arquivo)
        return {"text": " oi, tudo bem "}

    assert prov.transcrever(pedido("openai"), b"WAV", transporte_arquivo=envio) == "oi, tudo bem"
    assert vistos["url"].endswith("/audio/transcriptions") and vistos["campos"]["language"] == "pt"
    assert vistos["arquivo"][1] == "voz.wav" and "Bearer" in vistos["cab"]["authorization"]


@pytest.mark.parametrize("nome", ["claude", "deepseek"])
def test_ias_sem_voz_explicam_o_que_fazer(nome):
    with pytest.raises(ErroIA, match="não transcreve voz"):
        prov.transcrever(pedido(nome), b"WAV")


def test_multipart_monta_o_corpo():
    capturado = {}

    def falso(url, cab, corpo, timeout=0):
        capturado.update(cab=cab, corpo=corpo)
        return {"text": "ok"}

    original = prov.transporte_http
    prov.transporte_http = falso
    try:
        r = prov.transporte_multipart("http://x", {"authorization": "Bearer k"}, {"model": "m"}, ("file", "a.wav", b"DADOS", "audio/wav"))
    finally:
        prov.transporte_http = original
    assert r == {"text": "ok"} and "boundary=" in capturado["cab"]["content-type"]
    assert b'name="model"' in capturado["corpo"] and b"DADOS" in capturado["corpo"] and b'filename="a.wav"' in capturado["corpo"]
