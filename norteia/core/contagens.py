"""Contagem regressiva: dias que faltam para uma data (prova, viagem, aniversário)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .db import Banco
from .models import Registro, agora_utc


@dataclass
class Contagem:
    nome: str
    data: date
    cor: str = "#f5a623"
    anual: bool = False            # repete todo ano (aniversário)
    uuid: str = ""
    id: int | None = None

    def proxima_data(self, hoje: date) -> date:
        if not self.anual:
            return self.data
        try:
            d = self.data.replace(year=hoje.year)
        except ValueError:                      # 29/02 em ano não bissexto
            d = date(hoje.year, 3, 1)
        if d < hoje:
            try:
                d = self.data.replace(year=hoje.year + 1)
            except ValueError:
                d = date(hoje.year + 1, 3, 1)
        return d

    def dias(self, hoje: date | None = None) -> int:
        """Dias até a data (negativo se já passou)."""
        hoje = hoje or date.today()
        return (self.proxima_data(hoje) - hoje).days

    def texto(self, hoje: date | None = None) -> str:
        n = self.dias(hoje)
        if n == 0:
            return "É hoje!"
        if n > 0:
            return f"Falta {n} dia" if n == 1 else f"Faltam {n} dias"
        return f"Há {-n} dia" if n == -1 else f"Há {-n} dias"


class Contagens:
    def __init__(self, banco: Banco):
        self.banco = banco

    @staticmethod
    def _de(r: Registro) -> Contagem:
        d = r.dados
        return Contagem(d["nome"], date.fromisoformat(d["data"]), d.get("cor", "#f5a623"),
                        bool(d.get("anual", False)), r.uuid, r.id)

    @staticmethod
    def _dados(c: Contagem) -> dict:
        return {"nome": c.nome, "data": c.data.isoformat(), "cor": c.cor, "anual": c.anual}

    def criar(self, nome: str, data: date, cor: str = "#f5a623", anual: bool = False) -> Contagem:
        if not nome.strip():
            raise ValueError("a contagem precisa de um nome")
        c = Contagem(nome.strip(), data, cor, anual)
        r = self.banco.salvar_registro(Registro("contagem", self._dados(c)))
        c.uuid, c.id = r.uuid, r.id
        return c

    def salvar(self, c: Contagem) -> Contagem:
        r = self.banco.obter_registro_por_uuid(c.uuid)
        r.dados = self._dados(c)
        self.banco.salvar_registro(r)
        return c

    def listar(self, hoje: date | None = None) -> list[Contagem]:
        """Próximas primeiro; as que já passaram (e não repetem) vão para o fim."""
        hoje = hoje or date.today()
        todas = [self._de(r) for r in self.banco.listar_registros("contagem")]
        return sorted(todas, key=lambda c: (c.dias(hoje) < 0, abs(c.dias(hoje))))

    def apagar(self, uuid: str) -> None:
        r = self.banco.obter_registro_por_uuid(uuid)
        if r:
            r.apagado_em = agora_utc()
            self.banco.salvar_registro(r)
