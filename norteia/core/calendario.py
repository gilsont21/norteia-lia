"""Lógica das visões por data: calendário (dia, semana, mês, agenda), linha do tempo.

Aqui não há interface. A tela só desenha o que `Calendario.ocorrencias` devolve.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from dateutil.rrule import rrulestr

from . import ics
from .models import Tarefa

DURACAO_PADRAO_MIN = 60
COR_PADRAO = "#4772fa"
COR_EXTERNA = "#4dd0b1"


@dataclass(frozen=True)
class Ocorrencia:
    """Uma presença de tarefa ou evento externo no calendário."""
    titulo: str
    inicio: date                 # primeiro dia desta ocorrência
    fim: date                    # último dia (igual ao início se for de um dia só)
    hora: time | None            # None = dia inteiro
    duracao_min: int             # só vale quando tem hora
    cor: str
    tarefa: Tarefa | None = None
    virtual: bool = False        # repetição ainda não criada como tarefa de verdade
    externo: bool = False        # veio de uma assinatura de calendário (somente leitura)
    concluida: bool = False
    local: str = ""
    link: str = ""               # endereço do evento no Google Calendar (quando vier de lá)

    @property
    def dia_inteiro(self) -> bool:
        return self.hora is None

    @property
    def varios_dias(self) -> bool:
        return self.fim > self.inicio

    @property
    def fim_hora(self) -> time | None:
        if self.hora is None:
            return None
        total = self.hora.hour * 60 + self.hora.minute + self.duracao_min
        return time(min(total, 24 * 60 - 1) // 60, min(total, 24 * 60 - 1) % 60)

    def cobre(self, dia: date) -> bool:
        return self.inicio <= dia <= self.fim

    @property
    def editavel(self) -> bool:
        return self.tarefa is not None and not self.virtual and not self.externo


def inicio_da_semana(dia: date, segunda_primeiro: bool = False) -> date:
    """Domingo é o primeiro dia por padrão (como no calendário brasileiro)."""
    if segunda_primeiro:
        return dia - timedelta(days=dia.weekday())
    return dia - timedelta(days=(dia.weekday() + 1) % 7)


def grade_do_mes(ano: int, mes: int, segunda_primeiro: bool = False) -> list[date]:
    """42 dias (6 semanas) cobrindo o mês, para o desenho da grade."""
    primeiro = date(ano, mes, 1)
    comeco = inicio_da_semana(primeiro, segunda_primeiro)
    return [comeco + timedelta(days=i) for i in range(42)]


def _span(t: Tarefa) -> int:
    return max(0, (t.prazo - t.inicio).days) if t.inicio and t.prazo else 0


class Calendario:
    def __init__(self, servico):
        self.servico = servico
        self.banco = servico.banco

    def _cor(self, t: Tarefa, projetos: dict) -> str:
        p = projetos.get(t.projeto_id)
        return p.cor if p else COR_PADRAO

    def ocorrencias(self, ini: date, fim: date, incluir_finalizadas: bool = True,
                    externos: bool = True) -> list[Ocorrencia]:
        """Tudo que aparece entre `ini` e `fim` (inclusive), em ordem de dia e hora."""
        projetos = {p.id: p for p in self.banco.listar_projetos() + self.banco.listar_projetos_arquivados()}
        visiveis = {p.id for p in self.banco.listar_projetos()}
        sql = ("apagada_em IS NULL AND prazo IS NOT NULL AND COALESCE(inicio, prazo) <= ? "
               "AND (prazo >= ? OR repeticao IS NOT NULL)")
        saida: list[Ocorrencia] = []
        for t in self.banco.consultar(sql, (fim.isoformat(), ini.isoformat())):
            if t.projeto_id is not None and t.projeto_id not in visiveis:
                continue                      # lista arquivada ou apagada
            if t.finalizada and not incluir_finalizadas:
                continue
            cor = self._cor(t, projetos)
            span = _span(t)
            inicio_real = t.inicio or t.prazo
            if t.prazo >= ini:
                saida.append(Ocorrencia(
                    t.titulo, inicio_real, t.prazo, t.prazo_hora,
                    (t.duracao_min or DURACAO_PADRAO_MIN) if t.prazo_hora else 0, cor, t,
                    concluida=t.finalizada))
            if t.repeticao and not t.finalizada:
                saida += self._virtuais(t, cor, span, ini, fim)
        if externos:
            saida += self._externas(ini, fim)
        saida.sort(key=lambda o: (o.inicio, o.hora is not None, o.hora or time(0, 0), o.titulo.lower()))
        return saida

    def _virtuais(self, t: Tarefa, cor: str, span: int, ini: date, fim: date) -> list[Ocorrencia]:
        try:
            regra = rrulestr(t.repeticao, dtstart=datetime.combine(t.prazo, time(0, 0)))
        except (ValueError, KeyError):
            return []
        janela_ini = datetime.combine(max(t.prazo + timedelta(days=1), ini), time(0, 0))
        janela_fim = datetime.combine(fim + timedelta(days=span), time(23, 59, 59))
        saida = []
        for oc in regra.between(janela_ini, janela_fim, inc=True)[:400]:
            d = oc.date()
            if d <= t.prazo or d < ini:
                continue
            saida.append(Ocorrencia(
                t.titulo, d - timedelta(days=span), d, t.prazo_hora,
                (t.duracao_min or DURACAO_PADRAO_MIN) if t.prazo_hora else 0, cor, t, virtual=True))
        return saida

    def _externas(self, ini: date, fim: date) -> list[Ocorrencia]:
        saida: list[Ocorrencia] = []
        for ass in self.servico.assinaturas():
            if not ass.get("ativa", 1):
                continue                      # calendário do Google que você não marcou
            for l in self.banco.con.execute("SELECT * FROM evento_externo WHERE assinatura_id=?", (ass["id"],)):
                inicio = (datetime.fromisoformat(l["inicio"]) if "T" in l["inicio"]
                          else date.fromisoformat(l["inicio"]))
                fim_ev = None
                if l["fim"]:
                    fim_ev = datetime.fromisoformat(l["fim"]) if "T" in l["fim"] else date.fromisoformat(l["fim"])
                ev = ics.EventoICS(l["uid"], l["titulo"], inicio, fim_ev, local=l["local"], regra=l["regra"])
                hora = inicio.time() if isinstance(inicio, datetime) else None
                dur = 0
                if hora is not None and isinstance(fim_ev, datetime) and fim_ev.date() == inicio.date():
                    dur = max(15, int((fim_ev - inicio).total_seconds() // 60))
                elif hora is not None:
                    dur = DURACAO_PADRAO_MIN
                for p, u in ics.ocorrencias_do_evento(ev, ini, fim):
                    saida.append(Ocorrencia(l["titulo"], p, u, hora, dur, ass["cor"] or COR_EXTERNA,
                                            externo=True, local=l["local"], link=l["link"] or ""))
        return saida

    def por_dia(self, ini: date, fim: date, **kw) -> dict[date, list[Ocorrencia]]:
        """Mesmo conteúdo de `ocorrencias`, mas separado por dia (uma tarefa de vários dias aparece em cada dia)."""
        dias: dict[date, list[Ocorrencia]] = {ini + timedelta(days=i): [] for i in range((fim - ini).days + 1)}
        for o in self.ocorrencias(ini, fim, **kw):
            d = max(o.inicio, ini)
            while d <= min(o.fim, fim):
                dias[d].append(o)
                d += timedelta(days=1)
        return dias

    def agenda(self, desde: date, dias: int = 30, **kw) -> list[tuple[date, list[Ocorrencia]]]:
        """Só os dias que têm alguma coisa, para a visão "Agenda"."""
        mapa = self.por_dia(desde, desde + timedelta(days=dias - 1), **kw)
        return [(d, itens) for d, itens in mapa.items() if itens]


# ---------- edição pelas visões ----------
_MANTER = object()


def mover_para(servico, tarefa_id: int, dia: date, hora=_MANTER) -> Tarefa:
    """Arrasta a tarefa para outro dia (e, se informado, outra hora). Tarefa de vários dias mantém a duração."""
    t = servico.banco.obter_tarefa(tarefa_id)
    if t is None:
        raise ValueError("tarefa não encontrada")
    span = _span(t)
    t.prazo = dia + timedelta(days=span)
    t.inicio = dia if span else None
    if hora is not _MANTER:
        t.prazo_hora = hora
    return servico.salvar(t)


def definir_periodo(servico, tarefa_id: int, inicio: date, fim: date) -> Tarefa:
    """Define o período (ex.: esticar a barra na linha do tempo). `fim` não pode ser antes de `inicio`."""
    if fim < inicio:
        inicio, fim = fim, inicio
    t = servico.banco.obter_tarefa(tarefa_id)
    t.prazo = fim
    t.inicio = inicio if inicio != fim else None
    return servico.salvar(t)


def definir_duracao(servico, tarefa_id: int, minutos: int) -> Tarefa:
    t = servico.banco.obter_tarefa(tarefa_id)
    t.duracao_min = max(15, int(minutos))
    return servico.salvar(t)
