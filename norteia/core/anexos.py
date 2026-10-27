"""Anexos: cópias de arquivos guardadas na pasta de dados do app. Valem só neste aparelho."""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .models import agora_utc, novo_uuid

LIMITE_BYTES = 50 * 1024 * 1024


@dataclass
class Anexo:
    id: int
    uuid: str
    tarefa_id: int
    nome: str
    caminho: str
    tamanho: int


def _nome_seguro(nome: str) -> str:
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", os.path.basename(nome)).strip(" .")
    return nome or "arquivo"


class Anexos:
    def __init__(self, servico, pasta: str | Path | None):
        self.banco = servico.banco
        self.pasta = Path(pasta) / "anexos" if pasta else None

    def _exigir_pasta(self) -> Path:
        if self.pasta is None:
            raise RuntimeError("este app não tem pasta de dados configurada")
        return self.pasta

    def adicionar(self, tarefa_id: int, origem: str | Path) -> Anexo:
        base = self._exigir_pasta()
        origem = Path(origem)
        if not origem.is_file():
            raise ValueError("arquivo não encontrado")
        if origem.stat().st_size > LIMITE_BYTES:
            raise ValueError("arquivo maior que 50 MB")
        if self.banco.obter_tarefa(tarefa_id) is None:
            raise ValueError("tarefa não encontrada")
        uuid = novo_uuid()
        nome = _nome_seguro(origem.name)
        destino = base / uuid / nome
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origem, destino)
        cur = self.banco.con.execute(
            "INSERT INTO anexo(uuid, tarefa_id, nome, caminho, tamanho, criado_em) VALUES (?,?,?,?,?,?)",
            (uuid, tarefa_id, nome, str(destino), destino.stat().st_size, agora_utc().isoformat()))
        self.banco.con.commit()
        return Anexo(cur.lastrowid, uuid, tarefa_id, nome, str(destino), destino.stat().st_size)

    def listar(self, tarefa_id: int) -> list[Anexo]:
        return [Anexo(l["id"], l["uuid"], l["tarefa_id"], l["nome"], l["caminho"], l["tamanho"])
                for l in self.banco.con.execute("SELECT * FROM anexo WHERE tarefa_id=? ORDER BY id", (tarefa_id,))]

    def remover(self, anexo_id: int) -> None:
        l = self.banco.con.execute("SELECT * FROM anexo WHERE id=?", (anexo_id,)).fetchone()
        if l is None:
            return
        try:
            shutil.rmtree(Path(l["caminho"]).parent, ignore_errors=True)
        finally:
            self.banco.con.execute("DELETE FROM anexo WHERE id=?", (anexo_id,))
            self.banco.con.commit()
