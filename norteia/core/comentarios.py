"""Comentários e histórico de anotações de uma tarefa."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import Registro, agora_utc


@dataclass
class Comentario:
    tarefa_uuid: str
    texto: str
    criado_em: datetime            # UTC
    uuid: str = ""


class Comentarios:
    def __init__(self, servico):
        self.banco = servico.banco

    def adicionar(self, tarefa_id: int, texto: str) -> Comentario:
        texto = texto.strip()
        t = self.banco.obter_tarefa(tarefa_id)
        if t is None:
            raise ValueError("tarefa não encontrada")
        if not texto:
            raise ValueError("comentário vazio")
        criado = agora_utc()
        r = self.banco.salvar_registro(Registro(
            "comentario", {"tarefa": t.uuid, "texto": texto, "criado_em": criado.isoformat()}))
        return Comentario(t.uuid, texto, criado, r.uuid)

    def listar(self, tarefa_id: int) -> list[Comentario]:
        t = self.banco.obter_tarefa(tarefa_id)
        if t is None:
            return []
        itens = [Comentario(r.dados["tarefa"], r.dados["texto"], datetime.fromisoformat(r.dados["criado_em"]), r.uuid)
                 for r in self.banco.listar_registros("comentario") if r.dados.get("tarefa") == t.uuid]
        return sorted(itens, key=lambda c: c.criado_em)

    def editar(self, uuid: str, texto: str) -> None:
        r = self.banco.obter_registro_por_uuid(uuid)
        if r and texto.strip():
            r.dados["texto"] = texto.strip()
            self.banco.salvar_registro(r)

    def apagar(self, uuid: str) -> None:
        r = self.banco.obter_registro_por_uuid(uuid)
        if r:
            r.apagado_em = agora_utc()
            self.banco.salvar_registro(r)

    def quantidade(self, tarefa_id: int) -> int:
        return len(self.listar(tarefa_id))
