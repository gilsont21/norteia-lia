"""Foco: Pomodoro e cronômetro. O relógio é passado de fora (sem relógio escondido), então dá para testar."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .db import Banco
from .models import Registro

MIN_SESSAO_S = 60          # sessões interrompidas com menos de 1 minuto não são guardadas


@dataclass
class ConfigFoco:
    foco_min: int = 25
    pausa_curta_min: int = 5
    pausa_longa_min: int = 15
    ciclos_ate_pausa_longa: int = 4


@dataclass
class Sessao:
    inicio: datetime               # hora local em que começou
    duracao_s: int
    modo: str = "pomodoro"         # pomodoro ou cronometro
    completa: bool = True
    tarefa_uuid: str | None = None
    uuid: str | None = None


@dataclass
class Evento:
    tipo: str                      # "foco_completo" ou "pausa_completa"
    sessao: Sessao | None = None


class Cronometro:
    """Máquina de estados do foco.

    Pomodoro: foco -> pausa curta (ou longa a cada N ciclos) -> parado. Cronômetro: conta para cima até parar."""

    FOCO, PAUSA_CURTA, PAUSA_LONGA, PARADO = "foco", "pausa_curta", "pausa_longa", "parado"

    def __init__(self, config: ConfigFoco | None = None, modo: str = "pomodoro"):
        self.config = config or ConfigFoco()
        self.modo = modo
        self.fase = self.PARADO
        self.pausado = False
        self.ciclo = 0                       # focos completos desde a última pausa longa
        self.tarefa_uuid: str | None = None
        self._inicio: datetime | None = None
        self._acumulado = 0.0
        self._retomado: datetime | None = None

    # ---- relógio da fase ----
    def _comecar_fase(self, fase: str, agora: datetime) -> None:
        self.fase, self.pausado = fase, False
        self._inicio, self._acumulado, self._retomado = agora, 0.0, agora

    def decorrido(self, agora: datetime) -> float:
        if self.fase == self.PARADO:
            return 0.0
        extra = 0.0 if self.pausado or self._retomado is None else (agora - self._retomado).total_seconds()
        return self._acumulado + max(0.0, extra)

    @property
    def total_s(self) -> int | None:
        """Duração da fase em segundos (None no cronômetro, que não tem fim)."""
        if self.fase == self.PARADO or (self.modo == "cronometro" and self.fase == self.FOCO):
            return None
        minutos = {self.FOCO: self.config.foco_min, self.PAUSA_CURTA: self.config.pausa_curta_min,
                   self.PAUSA_LONGA: self.config.pausa_longa_min}[self.fase]
        return minutos * 60

    def restante(self, agora: datetime) -> float | None:
        total = self.total_s
        return None if total is None else max(0.0, total - self.decorrido(agora))

    @property
    def ativo(self) -> bool:
        return self.fase != self.PARADO

    # ---- comandos ----
    def iniciar(self, agora: datetime, tarefa_uuid: str | None = None) -> None:
        self.tarefa_uuid = tarefa_uuid
        self._comecar_fase(self.FOCO, agora)

    def pausar(self, agora: datetime) -> None:
        if self.ativo and not self.pausado:
            self._acumulado = self.decorrido(agora)
            self.pausado = True

    def retomar(self, agora: datetime) -> None:
        if self.ativo and self.pausado:
            self.pausado, self._retomado = False, agora

    def _sessao(self, agora: datetime, completa: bool) -> Sessao | None:
        segundos = int(round(self.decorrido(agora)))
        if self._inicio is None or (not completa and segundos < MIN_SESSAO_S):
            return None
        return Sessao(self._inicio, segundos, self.modo, completa, self.tarefa_uuid)

    def parar(self, agora: datetime) -> Sessao | None:
        """Encerra tudo. Se estava em foco, devolve a sessão (incompleta) para guardar."""
        sessao = self._sessao(agora, False) if self.fase == self.FOCO else None
        self.fase, self.pausado, self._inicio = self.PARADO, False, None
        return sessao

    def pular_pausa(self) -> None:
        if self.fase in (self.PAUSA_CURTA, self.PAUSA_LONGA):
            self.fase, self.pausado, self._inicio = self.PARADO, False, None

    def tick(self, agora: datetime) -> list[Evento]:
        """Chame uma vez por segundo. Devolve o que aconteceu (fim do foco ou da pausa)."""
        if not self.ativo or self.pausado:
            return []
        restante = self.restante(agora)
        if restante is None or restante > 0:
            return []
        if self.fase == self.FOCO:
            sessao = Sessao(self._inicio, self.config.foco_min * 60, self.modo, True, self.tarefa_uuid)
            self.ciclo += 1
            longa = self.ciclo >= self.config.ciclos_ate_pausa_longa
            if longa:
                self.ciclo = 0
            self._comecar_fase(self.PAUSA_LONGA if longa else self.PAUSA_CURTA, agora)
            return [Evento("foco_completo", sessao)]
        self.fase, self.pausado, self._inicio = self.PARADO, False, None
        return [Evento("pausa_completa")]


class Foco:
    """Guarda e consulta as sessões de foco."""

    def __init__(self, banco: Banco):
        self.banco = banco

    def registrar(self, s: Sessao) -> Registro:
        dados = {"inicio": s.inicio.isoformat(), "duracao_s": int(s.duracao_s), "modo": s.modo,
                 "completa": s.completa, "tarefa": s.tarefa_uuid}
        r = Registro("foco", dados)
        if s.uuid:
            r.uuid = s.uuid
        saved = self.banco.salvar_registro(r)
        s.uuid = saved.uuid
        return saved

    def sessoes(self, ini: date | None = None, fim: date | None = None) -> list[Sessao]:
        saida = []
        for r in self.banco.listar_registros("foco"):
            d = r.dados
            inicio = datetime.fromisoformat(d["inicio"])
            if (ini and inicio.date() < ini) or (fim and inicio.date() > fim):
                continue
            saida.append(Sessao(inicio, int(d["duracao_s"]), d.get("modo", "pomodoro"),
                                bool(d.get("completa", True)), d.get("tarefa"), r.uuid))
        return sorted(saida, key=lambda s: s.inicio)

    def segundos_por_dia(self, ini: date, fim: date) -> dict[date, int]:
        dias = {ini + timedelta(days=i): 0 for i in range((fim - ini).days + 1)}
        for s in self.sessoes(ini, fim):
            dias[s.inicio.date()] += s.duracao_s
        return dias

    def segundos_da_tarefa(self, tarefa_uuid: str) -> int:
        return sum(s.duracao_s for s in self.sessoes() if s.tarefa_uuid == tarefa_uuid)

    def apagar(self, uuid: str) -> None:
        from .models import agora_utc
        r = self.banco.obter_registro_por_uuid(uuid)
        if r:
            r.apagado_em = agora_utc()
            self.banco.salvar_registro(r)


def formatar_duracao(segundos: int) -> str:
    """90 -> "1 min", 3700 -> "1 h 01 min", 0 -> "0 min"."""
    minutos = int(segundos) // 60
    if minutos < 60:
        return f"{minutos} min"
    return f"{minutos // 60} h {minutos % 60:02d} min"
