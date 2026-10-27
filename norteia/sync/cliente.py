"""Lado do aparelho: manda o que mudou, recebe o que mudou nos outros."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from ..core.db import Banco
from ..core.models import agora_utc
from .serial import aplicar, empacotar


class ErroSincronizacao(Exception):
    pass


@dataclass
class Resumo:
    enviados: int = 0
    recebidos: int = 0
    pendentes: int = 0

    def __str__(self) -> str:
        return f"{self.enviados} enviado(s), {self.recebidos} recebido(s)"


def transporte_http(url_base: str, token: str, timeout: float = 15.0):
    """Cria a função que faz o POST de verdade (usa só a biblioteca padrão)."""
    def enviar(caminho: str, corpo: dict) -> dict:
        req = urllib.request.Request(
            url_base.rstrip("/") + caminho, data=json.dumps(corpo).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise ErroSincronizacao("Token recusado pelo servidor.") from e
            raise ErroSincronizacao(f"O servidor respondeu erro {e.code}.") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ErroSincronizacao(f"Não consegui falar com o servidor: {e}") from e
    return enviar


class Sincronizador:
    """Três passos separados (preparar, enviar, aplicar) para a tela poder fazer o envio
    numa thread sem tocar no banco fora da thread principal."""

    def __init__(self, banco: Banco, transporte):
        self.banco = banco
        self.transporte = transporte

    def preparar(self) -> dict:
        marco = agora_utc()
        ultimo = self.banco.meta("sync_enviado_ate")
        pacote = empacotar(self.banco, datetime.fromisoformat(ultimo) if ultimo else None)
        return {
            "dispositivo": self.banco.id_dispositivo(),
            "depois_de": int(self.banco.meta("sync_seq", "0")),
            "pacote": pacote,
            "_marco": marco.isoformat(),
        }

    def enviar(self, pedido: dict) -> dict:
        corpo = {k: v for k, v in pedido.items() if not k.startswith("_")}
        return self.transporte("/sincronizar", corpo)

    def aplicar(self, pedido: dict, resposta: dict) -> Resumo:
        recebido = aplicar(self.banco, resposta["pacote"])
        self.banco.definir_meta("sync_seq", str(resposta["seq"]))
        self.banco.definir_meta("sync_enviado_ate", pedido["_marco"])
        p = pedido["pacote"]
        return Resumo(
            enviados=len(p["projetos"]) + len(p["filtros"]) + len(p["tarefas"]) + len(p.get("registros", [])),
            recebidos=len(recebido.aceitos),
            pendentes=len(recebido.pendentes) + len(resposta.get("pendentes", [])),
        )

    def sincronizar(self) -> Resumo:
        pedido = self.preparar()
        return self.aplicar(pedido, self.enviar(pedido))
