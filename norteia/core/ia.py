"""Sugestão de subtarefas com a API do Claude. Opcional: só roda quando você clica no botão.

Só o título e as notas da tarefa escolhida são enviados. A chave fica em ~/.tarefas/config.json
(ou na variável de ambiente ANTHROPIC_API_KEY). Sem chave, nada é enviado.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

URL = "https://api.anthropic.com/v1/messages"
MODELO_PADRAO = "claude-sonnet-4-5"
VERSAO_API = "2023-06-01"


class ErroIA(Exception):
    pass


def transporte_http(url: str, cabecalhos: dict, corpo: bytes, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(url, data=corpo, headers=cabecalhos, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalhe = ""
        try:
            detalhe = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except (ValueError, OSError):
            pass
        if e.code in (401, 403):
            raise ErroIA("A chave da API foi recusada. Confira em Configurações.") from e
        raise ErroIA(f"A API respondeu com erro {e.code}. {detalhe}".strip()) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErroIA(f"Não consegui falar com a API: {e}") from e


def chave_da_api(prefs: dict | None = None) -> str:
    return ((prefs or {}).get("claude_api_key") or os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def _extrair_lista(texto: str) -> list[str]:
    """Aceita a lista pura, dentro de ```json ... ``` ou cercada de texto."""
    achado = re.search(r"\[.*\]", texto, flags=re.S)
    if not achado:
        raise ErroIA("A resposta não veio em formato de lista.")
    try:
        bruto = json.loads(achado.group(0))
    except ValueError as e:
        raise ErroIA("A resposta não veio em formato de lista.") from e
    saida = []
    for item in bruto:
        if isinstance(item, str) and item.strip():
            limpo = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", item.strip())
            if limpo and limpo not in saida:
                saida.append(limpo[:200])
    return saida


def quebrar(titulo: str, notas: str = "", chave: str | None = None, modelo: str | None = None,
            transporte=transporte_http, maximo: int = 8) -> list[str]:
    """Devolve até `maximo` subtarefas curtas e acionáveis para a tarefa."""
    if not chave:
        raise ErroIA("Falta a chave da API do Claude (Configurações).")
    if not titulo.strip():
        raise ErroIA("A tarefa precisa de um título.")
    pedido = (f"Quebre a tarefa abaixo em no máximo {maximo} subtarefas curtas, concretas e em ordem de execução. "
              "Responda SOMENTE com uma lista JSON de textos em português do Brasil, sem comentários.\n\n"
              f"Tarefa: {titulo.strip()}\n" + (f"Detalhes: {notas.strip()[:2000]}\n" if notas.strip() else ""))
    corpo = json.dumps({"model": modelo or MODELO_PADRAO, "max_tokens": 600,
                        "messages": [{"role": "user", "content": pedido}]}).encode("utf-8")
    cabecalhos = {"content-type": "application/json", "x-api-key": chave, "anthropic-version": VERSAO_API}
    resposta = transporte(URL, cabecalhos, corpo)
    texto = "".join(b.get("text", "") for b in resposta.get("content", []) if b.get("type") == "text")
    lista = _extrair_lista(texto)[:maximo]
    if not lista:
        raise ErroIA("A resposta veio vazia.")
    return lista
