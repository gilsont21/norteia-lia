"""Servidor de sincronização (FastAPI).

Guarda uma cópia completa dos dados e um registro numerado das alterações. Cada aparelho
manda o que mudou e recebe o que os outros mudaram desde a última vez.

Rodar:  NORTEIA_TOKEN=uma-senha-longa python -m norteia.sync.servidor --banco servidor.db
Exponha só dentro de uma rede privada (ex.: Tailscale) ou atrás de HTTPS.
"""
from __future__ import annotations

import argparse
import hmac
import os
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from ..core.db import Banco
from .serial import aplicar, pacote_de


class PedidoSync(BaseModel):
    dispositivo: str
    depois_de: int = 0
    pacote: dict = {}


def criar_app(banco: Banco, token: str) -> FastAPI:
    if len(token) < 8:
        raise ValueError("o token precisa ter pelo menos 8 caracteres")
    app = FastAPI(title="Tarefas: sincronização")
    trava = threading.Lock()

    def autenticar(authorization: str = Header(default="")):
        esperado = f"Bearer {token}"
        if not hmac.compare_digest(authorization.encode(), esperado.encode()):
            raise HTTPException(status_code=401, detail="token inválido")

    @app.get("/saude")
    def saude():
        return {"ok": True}

    @app.post("/sincronizar", dependencies=[Depends(autenticar)])
    def sincronizar(pedido: PedidoSync):
        with trava:
            resultado = aplicar(banco, pedido.pacote)
            proprios = set(resultado.aceitos)
            for tipo, uuid in resultado.aceitos:
                banco.registrar_alteracao(tipo, uuid)
            novos = [(tipo, uuid) for _seq, tipo, uuid in banco.alteracoes_depois_de(pedido.depois_de)
                     if (tipo, uuid) not in proprios]
            return {
                "seq": banco.ultima_alteracao(),
                "pacote": pacote_de(banco, novos),
                "pendentes": resultado.pendentes,
            }

    return app


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(description="Servidor de sincronização do app de tarefas")
    ap.add_argument("--banco", default="servidor.db")
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 só dentro de rede privada")
    ap.add_argument("--porta", type=int, default=8765)
    args = ap.parse_args()
    token = os.environ.get("NORTEIA_TOKEN", "")
    if not token:
        raise SystemExit("Defina a variável de ambiente NORTEIA_TOKEN com uma senha longa.")
    banco = Banco(Path(args.banco), varias_threads=True)
    uvicorn.run(criar_app(banco, token), host=args.host, port=args.porta)


if __name__ == "__main__":
    main()
