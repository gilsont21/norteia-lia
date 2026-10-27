import json

import pytest

from norteia.core import ia


def resposta(texto: str) -> dict:
    return {"content": [{"type": "text", "text": texto}]}


def test_quebrar_monta_o_pedido_e_le_a_lista():
    visto = {}

    def transporte(url, cab, corpo):
        visto.update(url=url, cab=cab, corpo=json.loads(corpo))
        return resposta('Claro!\n```json\n["1. Reunir documentos", "- Ler o edital", "Reunir documentos", "  "]\n```')

    r = ia.quebrar("Organizar prestação de contas", "do convênio", "sk-teste", transporte=transporte)
    assert r == ["Reunir documentos", "Ler o edital"]
    assert visto["url"] == ia.URL and visto["cab"]["x-api-key"] == "sk-teste"
    assert visto["cab"]["anthropic-version"] == ia.VERSAO_API
    assert visto["corpo"]["model"] == ia.MODELO_PADRAO
    texto = visto["corpo"]["messages"][0]["content"]
    assert "Organizar prestação de contas" in texto and "do convênio" in texto


def test_quebrar_limita_quantidade_e_usa_modelo_escolhido():
    itens = json.dumps([f"passo {i}" for i in range(20)])
    visto = {}

    def transporte(url, cab, corpo):
        visto["modelo"] = json.loads(corpo)["model"]
        return resposta(itens)

    assert len(ia.quebrar("x", chave="k", modelo="outro-modelo", transporte=transporte, maximo=5)) == 5
    assert visto["modelo"] == "outro-modelo"


def test_quebrar_erros():
    with pytest.raises(ia.ErroIA, match="chave"):
        ia.quebrar("x", chave="")
    with pytest.raises(ia.ErroIA, match="título"):
        ia.quebrar("  ", chave="k")
    with pytest.raises(ia.ErroIA, match="lista"):
        ia.quebrar("x", chave="k", transporte=lambda *a: resposta("não sei"))
    with pytest.raises(ia.ErroIA, match="lista"):
        ia.quebrar("x", chave="k", transporte=lambda *a: resposta("[quebrado"))
    with pytest.raises(ia.ErroIA, match="vazia"):
        ia.quebrar("x", chave="k", transporte=lambda *a: resposta("[]"))


def test_chave_da_api_prefere_a_das_preferencias(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "do-ambiente")
    assert ia.chave_da_api({"claude_api_key": " da-config "}) == "da-config"
    assert ia.chave_da_api({}) == "do-ambiente"
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert ia.chave_da_api(None) == ""
