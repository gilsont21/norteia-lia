"""Hábitos: coisas que você quer repetir (beber água, treinar) com meta por dia e sequência.

Cada hábito e cada marcação de dia é um `Registro` (sincroniza entre aparelhos). A marcação de um dia
tem uuid fixo (hábito + data), então dois aparelhos que marcam o mesmo dia não duplicam.
"""
from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .db import Banco
from .models import Registro, agora_utc

_NS = _uuid.UUID("8d2f6c4e-3b1a-4c7e-9f50-0a7e1d5c2b11")
TODOS_OS_DIAS = [0, 1, 2, 3, 4, 5, 6]          # 0 = segunda ... 6 = domingo
NOMES_DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
SECOES = ["Manhã", "Tarde", "Noite", "Outros"]


@dataclass
class Habito:
    nome: str
    cor: str = "#4dd0b1"
    meta: int = 1                                  # vezes por dia (1 = só marcar)
    unidade: str = "vez"
    dias: list[int] = field(default_factory=lambda: list(TODOS_OS_DIAS))
    lembrete: str | None = None                    # "HH:MM"
    inicio: date = field(default_factory=date.today)
    arquivado: bool = False
    ordem: int = 0
    uuid: str = field(default_factory=lambda: str(_uuid.uuid4()))
    id: int | None = None
    secao: str = "Outros"                          # Manhã, Tarde, Noite ou Outros
    dias_meta: int = 0                             # 0 = para sempre; N = o hábito vale por N dias a partir do início

    @property
    def fim(self) -> date | None:
        return self.inicio + timedelta(days=self.dias_meta - 1) if self.dias_meta > 0 else None

    def agendado(self, dia: date) -> bool:
        if dia < self.inicio or dia.weekday() not in self.dias:
            return False
        return self.dias_meta <= 0 or dia <= self.fim


class Habitos:
    def __init__(self, banco: Banco):
        self.banco = banco

    # ---- conversão ----
    @staticmethod
    def _dados(h: Habito) -> dict:
        return {"nome": h.nome, "cor": h.cor, "meta": h.meta, "unidade": h.unidade, "dias": sorted(h.dias),
                "lembrete": h.lembrete, "inicio": h.inicio.isoformat(), "arquivado": h.arquivado,
                "ordem": h.ordem, "secao": h.secao, "dias_meta": h.dias_meta}

    @staticmethod
    def _habito(r: Registro) -> Habito:
        d = r.dados
        return Habito(d["nome"], d.get("cor", "#4dd0b1"), int(d.get("meta", 1)), d.get("unidade", "vez"),
                      list(d.get("dias", TODOS_OS_DIAS)), d.get("lembrete"),
                      date.fromisoformat(d["inicio"]), bool(d.get("arquivado", False)),
                      int(d.get("ordem", 0)), r.uuid, r.id,
                      d.get("secao") if d.get("secao") in SECOES else "Outros", max(0, int(d.get("dias_meta", 0))))

    # ---- hábitos ----
    def criar(self, nome: str, cor: str = "#4dd0b1", meta: int = 1, unidade: str = "vez",
              dias: list[int] | None = None, lembrete: str | None = None, inicio: date | None = None,
              secao: str = "Outros", dias_meta: int = 0) -> Habito:
        nome = nome.strip()
        if not nome:
            raise ValueError("o hábito precisa de um nome")
        h = Habito(nome, cor, max(1, int(meta)), unidade or "vez", sorted(dias) if dias else list(TODOS_OS_DIAS),
                   lembrete, inicio or date.today(), ordem=len(self.listar(arquivados=None)),
                   secao=secao if secao in SECOES else "Outros", dias_meta=max(0, int(dias_meta or 0)))
        r = self.banco.salvar_registro(Registro("habito", self._dados(h), h.uuid))
        h.id = r.id
        return h

    def listar(self, arquivados: bool | None = False) -> list[Habito]:
        """`arquivados=False` só os ativos, `True` só os arquivados, `None` todos."""
        hs = [self._habito(r) for r in self.banco.listar_registros("habito")]
        if arquivados is not None:
            hs = [h for h in hs if h.arquivado == arquivados]
        return sorted(hs, key=lambda h: (h.ordem, h.id or 0))

    def obter(self, uuid: str) -> Habito | None:
        r = self.banco.obter_registro_por_uuid(uuid)
        return self._habito(r) if r and r.tipo == "habito" and r.apagado_em is None else None

    def salvar(self, h: Habito) -> Habito:
        r = self.banco.obter_registro_por_uuid(h.uuid)
        r.dados = self._dados(h)
        self.banco.salvar_registro(r)
        return h

    def arquivar(self, uuid: str, sim: bool = True) -> None:
        h = self.obter(uuid)
        h.arquivado = sim
        self.salvar(h)

    def apagar(self, uuid: str) -> None:
        r = self.banco.obter_registro_por_uuid(uuid)
        r.apagado_em = agora_utc()
        self.banco.salvar_registro(r)
        for m in self.banco.listar_registros("marcacao"):
            if m.dados.get("habito") == uuid:
                m.apagado_em = agora_utc()
                self.banco.salvar_registro(m)

    # ---- marcações ----
    @staticmethod
    def _uuid_marcacao(habito_uuid: str, dia: date) -> str:
        return str(_uuid.uuid5(_NS, f"{habito_uuid}:{dia.isoformat()}"))

    def marcacoes(self, h: Habito) -> dict[date, int]:
        return {date.fromisoformat(r.dados["dia"]): int(r.dados["qtd"])
                for r in self.banco.listar_registros("marcacao") if r.dados.get("habito") == h.uuid}

    def todas_as_marcacoes(self) -> dict[str, dict[date, int]]:
        saida: dict[str, dict[date, int]] = {}
        for r in self.banco.listar_registros("marcacao"):
            saida.setdefault(r.dados["habito"], {})[date.fromisoformat(r.dados["dia"])] = int(r.dados["qtd"])
        return saida

    def quantidade(self, h: Habito, dia: date) -> int:
        r = self.banco.obter_registro_por_uuid(self._uuid_marcacao(h.uuid, dia))
        return int(r.dados["qtd"]) if r and r.apagado_em is None else 0

    def definir_quantidade(self, h: Habito, dia: date, qtd: int) -> int:
        qtd = max(0, min(int(qtd), 9999))
        uid = self._uuid_marcacao(h.uuid, dia)
        r = self.banco.obter_registro_por_uuid(uid)
        dados = {"habito": h.uuid, "dia": dia.isoformat(), "qtd": qtd}
        if r is None:
            self.banco.salvar_registro(Registro("marcacao", dados, uid))
        else:
            r.dados, r.apagado_em = dados, None
            self.banco.salvar_registro(r)
        return qtd

    def concluido(self, h: Habito, dia: date) -> bool:
        return self.quantidade(h, dia) >= h.meta

    def alternar(self, h: Habito, dia: date) -> int:
        """Marca o dia como feito (ou desmarca, se já estava feito)."""
        return self.definir_quantidade(h, dia, 0 if self.concluido(h, dia) else h.meta)

    def incrementar(self, h: Habito, dia: date) -> int:
        """+1 na quantidade do dia (para metas como "8 copos"); passando da meta, zera."""
        atual = self.quantidade(h, dia)
        return self.definir_quantidade(h, dia, 0 if atual >= h.meta else atual + 1)

    # ---- números ----
    def sequencia(self, h: Habito, hoje: date | None = None,
                  marcacoes: dict[date, int] | None = None) -> tuple[int, int]:
        """(sequência atual, melhor sequência), contando só os dias em que o hábito estava marcado para valer.

        Se hoje ainda não foi feito, a sequência atual não quebra (ainda dá tempo)."""
        hoje = hoje or date.today()
        marc = marcacoes if marcacoes is not None else self.marcacoes(h)
        melhor = atual = 0
        dia = h.inicio
        while dia <= hoje:
            if h.agendado(dia):
                if marc.get(dia, 0) >= h.meta:
                    atual += 1
                    melhor = max(melhor, atual)
                elif dia != hoje:
                    atual = 0
            dia += timedelta(days=1)
        return atual, melhor

    def taxa(self, h: Habito, ini: date, fim: date, marcacoes: dict[date, int] | None = None) -> float:
        marc = marcacoes if marcacoes is not None else self.marcacoes(h)
        previstos = feitos = 0
        dia = max(ini, h.inicio)
        while dia <= fim:
            if h.agendado(dia):
                previstos += 1
                feitos += marc.get(dia, 0) >= h.meta
            dia += timedelta(days=1)
        return feitos / previstos if previstos else 0.0

    def total_feitos(self, h: Habito, marcacoes: dict[date, int] | None = None) -> int:
        marc = marcacoes if marcacoes is not None else self.marcacoes(h)
        return sum(1 for q in marc.values() if q >= h.meta)

    def mes(self, h: Habito, ano: int, mes: int, hoje: date | None = None) -> list[tuple[date, str]]:
        """Estado de cada dia do mês: feito, parcial, perdido, pendente (hoje), futuro ou livre (não vale nesse dia)."""
        hoje = hoje or date.today()
        marc = self.marcacoes(h)
        saida = []
        dia = date(ano, mes, 1)
        while dia.month == mes:
            q = marc.get(dia, 0)
            if q >= h.meta and q > 0:
                estado = "feito"
            elif not h.agendado(dia):
                estado = "livre"
            elif dia > hoje:
                estado = "futuro"
            elif q > 0:
                estado = "parcial"
            elif dia == hoje:
                estado = "pendente"
            else:
                estado = "perdido"
            saida.append((dia, estado))
            dia += timedelta(days=1)
        return saida

    def pendentes_hoje(self, hoje: date | None = None) -> list[Habito]:
        hoje = hoje or date.today()
        return [h for h in self.listar() if h.agendado(hoje) and not self.concluido(h, hoje)]

    # ---- lembretes do hábito ----
    def lembretes_vencidos(self, agora: datetime | None = None) -> list[Habito]:
        agora = agora or datetime.now()
        hoje = agora.date()
        saida = []
        for h in self.pendentes_hoje(hoje):
            if not h.lembrete:
                continue
            hora = datetime.strptime(h.lembrete, "%H:%M").time()
            if agora.time() >= hora and self.banco.meta(f"habito_avisado:{h.uuid}") != hoje.isoformat():
                saida.append(h)
        return saida

    def marcar_avisado(self, h: Habito, hoje: date | None = None) -> None:
        self.banco.definir_meta(f"habito_avisado:{h.uuid}", (hoje or date.today()).isoformat())
