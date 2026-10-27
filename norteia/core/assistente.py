"""Assistente de IA: conversa, lê o estado do app e propõe mudanças que só valem depois de você confirmar.

Como funciona um turno:
  1. você escreve; o assistente manda para a IA o resumo do dia e as ferramentas disponíveis;
  2. a IA pode pedir ferramentas de LEITURA (ver tarefas, agenda, estatísticas), que rodam na hora;
  3. as ferramentas de ESCRITA (criar, mudar, concluir, apagar) não mexem em nada: viram um *plano*;
  4. você vê o plano, clica em Aplicar, e o app executa tudo como um lote que dá para DESFAZER.

A rede roda em outra thread com uma conexão própria do banco (como o Google), por isso `turno` só lê.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from dateutil import tz

from .arquivos_ia import descricao_para_guardar
from .ia import ErroIA
from .ia_provedores import Pedido, conversar, transporte_http
from .models import Prioridade, Tarefa, agora_utc

MAX_PASSOS = 6
MAX_LISTAGEM = 60
DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
PRIORIDADES = {"nenhuma": Prioridade.NENHUMA, "baixa": Prioridade.BAIXA, "media": Prioridade.MEDIA,
               "média": Prioridade.MEDIA, "alta": Prioridade.ALTA}
NOME_PRIORIDADE = {0: "nenhuma", 1: "baixa", 2: "media", 3: "alta"}


def _obj(propriedades: dict, obrigatorios: list[str] | None = None) -> dict:
    return {"type": "object", "properties": propriedades, "required": obrigatorios or []}


_S = {"type": "string"}
_I = {"type": "integer"}
_CAMPOS_TAREFA = {
    "titulo": {"type": "string", "description": "título curto"},
    "data": {"type": "string", "description": "AAAA-MM-DD. Em atualizar, texto vazio tira a data."},
    "hora": {"type": "string", "description": "HH:MM (24 h). Em atualizar, texto vazio vira dia inteiro."},
    "duracao_min": {"type": "integer", "description": "duração no calendário, em minutos"},
    "prioridade": {"type": "string", "enum": ["nenhuma", "baixa", "media", "alta"]},
    "lista": {"type": "string", "description": "nome de uma lista existente (ou criada antes neste plano)"},
    "etiquetas": {"type": "array", "items": {"type": "string"}},
    "notas": {"type": "string"},
}

FERRAMENTAS_LEITURA = [
    {"nome": "listar_tarefas",
     "descricao": "Lista tarefas abertas. filtro: hoje, amanha, proximos (7 dias), atrasadas, todas, caixa, "
                  "concluidas ou o nome de uma lista.",
     "parametros": _obj({"filtro": _S, "limite": _I}, ["filtro"])},
    {"nome": "buscar_tarefas", "descricao": "Procura tarefas por texto no título, notas ou etiqueta.",
     "parametros": _obj({"texto": _S}, ["texto"])},
    {"nome": "ver_agenda",
     "descricao": "Mostra a agenda por dia (tarefas com data e eventos do Google Calendar) entre duas datas "
                  "(no máximo 31 dias).",
     "parametros": _obj({"inicio": {"type": "string", "description": "AAAA-MM-DD"},
                         "fim": {"type": "string", "description": "AAAA-MM-DD"}}, ["inicio", "fim"])},
    {"nome": "ver_listas", "descricao": "Lista as listas, com pasta e quantidade de tarefas abertas.",
     "parametros": _obj({})},
    {"nome": "ver_estatisticas",
     "descricao": "Números da rotina: concluídas por dia (14 dias), por lista, horários em que mais conclui, "
                  "atrasadas, sequência de dias.",
     "parametros": _obj({})},
]
FERRAMENTAS_ESCRITA = [
    {"nome": "criar_tarefa", "descricao": "Propõe criar uma tarefa.",
     "parametros": _obj({k: _CAMPOS_TAREFA[k] for k in _CAMPOS_TAREFA}, ["titulo"])},
    {"nome": "atualizar_tarefa",
     "descricao": "Propõe mudar campos de uma tarefa existente (só os que você enviar). Serve para reagendar.",
     "parametros": _obj({"id": _I, **_CAMPOS_TAREFA}, ["id"])},
    {"nome": "concluir_tarefa", "descricao": "Propõe marcar uma tarefa como concluída.",
     "parametros": _obj({"id": _I}, ["id"])},
    {"nome": "apagar_tarefa", "descricao": "Propõe mandar uma tarefa para a lixeira.",
     "parametros": _obj({"id": _I}, ["id"])},
    {"nome": "criar_lista", "descricao": "Propõe criar uma lista nova.", "parametros": _obj({"nome": _S}, ["nome"])},
    {"nome": "guardar_preferencia",
     "descricao": "Propõe guardar uma preferência fixa do usuário (ex.: 'não marcar nada antes das 8h'). "
                  "Use só quando ele pedir para lembrar.",
     "parametros": _obj({"texto": _S}, ["texto"])},
]
FERRAMENTAS = FERRAMENTAS_LEITURA + FERRAMENTAS_ESCRITA
NOMES_ESCRITA = {f["nome"] for f in FERRAMENTAS_ESCRITA}


# ---------------------------------------------------------------- plano e lote
@dataclass
class Acao:
    tipo: str
    args: dict
    resumo: str


@dataclass
class Plano:
    acoes: list[Acao] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.acoes)


@dataclass
class Turno:
    historico: list[dict]
    texto: str
    plano: Plano


@dataclass
class Lote:
    """O que foi aplicado, com o necessário para desfazer."""
    desfazer: list[tuple] = field(default_factory=list)
    resumos: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)
    desfeito: bool = False

    @property
    def total(self) -> int:
        return len(self.resumos)


def _fmt_data(d: date | None) -> str:
    return d.strftime("%d/%m") if d else "sem data"


def _fmt_hora(h: time | None) -> str:
    return h.strftime("%H:%M") if h else "dia inteiro"


def _data(texto) -> date | None:
    texto = (texto or "").strip() if isinstance(texto, str) else ""
    if not texto:
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError as e:
        raise ValueError(f"data inválida: {texto!r} (use AAAA-MM-DD)") from e


def _hora(texto) -> time | None:
    texto = (texto or "").strip() if isinstance(texto, str) else ""
    if not texto:
        return None
    try:
        h = time.fromisoformat(texto)
    except ValueError as e:
        raise ValueError(f"hora inválida: {texto!r} (use HH:MM)") from e
    return h.replace(second=0, microsecond=0)


# ---------------------------------------------------------------- assistente
class Assistente:
    def __init__(self, servico, pedido: Pedido, transporte=transporte_http, hoje: date | None = None,
                 agora: datetime | None = None):
        self.servico, self.banco, self.pedido, self.transporte = servico, servico.banco, pedido, transporte
        self.agora = agora or datetime.now()
        self.hoje = hoje or self.agora.date()
        self._plano = Plano()
        self._listas_novas: set[str] = set()

    # ---- instruções para a IA
    def sistema(self) -> str:
        h = self.hoje
        listas = [p.nome for p in self.banco.listar_projetos()]
        c = self.servico.contagens(h)
        from .servico import AMANHA, HOJE, PROXIMOS, TODAS  # noqa: PLC0415
        linhas = [
            "Você é o assistente de organização de um app de tarefas pessoal. Ajude a pessoa a planejar a rotina, "
            "priorizar, reagendar e arrumar listas. Responda em português do Brasil, curto e direto, sem enrolar.",
            f"Hoje é {DIAS_SEMANA[h.weekday()]}, {h.isoformat()}, agora são {self.agora:%H:%M}.",
            f"Tarefas abertas: {c.get(TODAS, 0)}. Para hoje (incluindo atrasadas): {c.get(HOJE, 0)}. "
            f"Amanhã: {c.get(AMANHA, 0)}. Próximos 7 dias: {c.get(PROXIMOS, 0)}.",
            "Listas: " + (", ".join(listas) if listas else "(nenhuma)") + ".",
            "Regras: use as ferramentas de leitura para ver os dados reais; nunca invente ids nem tarefas. "
            "As ferramentas de escrita só PROPÕEM mudanças: nada é feito até a pessoa clicar em Aplicar. "
            "Depois de propor, explique o plano em poucas linhas e peça para ela revisar. "
            "Evite horários antes das 7h e depois das 22h, a não ser que a pessoa peça. "
            "Antes de reagendar, olhe a agenda (ver_agenda) para não marcar em cima de eventos. "
            "Se a pessoa anexar imagem, PDF ou texto (print de grade de aulas, calendário da faculdade, lista de "
            "afazeres, e-mail), leia o conteúdo, diga em poucas linhas o que entendeu e proponha as tarefas com "
            "criar_tarefa. Datas relativas ('segunda', 'dia 12') valem em relação a hoje; se algo for ambíguo, "
            "pergunte antes de propor.",
        ]
        if self.pedido.preferencias:
            linhas.append("Preferências fixas da pessoa: " + " | ".join(self.pedido.preferencias))
        return "\n".join(linhas)

    # ---- um turno de conversa
    def turno(self, historico: list[dict], texto: str, anexos: list[dict] | None = None) -> Turno:
        historico = copy.deepcopy(historico)
        msg_usuario = {"papel": "usuario", "texto": texto}
        if anexos:
            msg_usuario["anexos"] = anexos
        historico.append(msg_usuario)
        self._plano = Plano()
        final = ""
        for _ in range(MAX_PASSOS):
            r = conversar(self.pedido, self.sistema(), historico, FERRAMENTAS, self.transporte)
            msg = {"papel": "assistente", "texto": r.texto,
                   "chamadas": [{"id": c.id, "nome": c.nome, "args": c.args} for c in r.chamadas]}
            if r.bruto:
                msg["bruto_gemini"] = r.bruto
            historico.append(msg)
            if not r.chamadas:
                final = r.texto
                break
            resultados = [{"id": c.id, "nome": c.nome, "conteudo": self._executar(c.nome, c.args)} for c in r.chamadas]
            historico.append({"papel": "ferramenta", "resultados": resultados})
        else:
            final = "Parei aqui para não rodar em círculos. Me diga como você quer continuar."
            historico.append({"papel": "assistente", "texto": final, "chamadas": []})
        return Turno(historico, final.strip(), self._plano)

    def _executar(self, nome: str, args: dict) -> str:
        try:
            if nome in NOMES_ESCRITA:
                return self._propor(nome, args)
            return json.dumps(getattr(self, "_ler_" + nome)(**self._so_conhecidos(nome, args)),
                              ensure_ascii=False, default=str)
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            return f"erro: {e}"

    @staticmethod
    def _so_conhecidos(nome: str, args: dict) -> dict:
        ferr = next((f for f in FERRAMENTAS if f["nome"] == nome), None)
        if ferr is None:
            raise ValueError(f"ferramenta desconhecida: {nome}")
        return {k: v for k, v in args.items() if k in ferr["parametros"]["properties"]}

    # ---- leitura
    def _tarefa_json(self, t, nomes: dict) -> dict:
        d = {"id": t.id, "titulo": t.titulo, "data": t.prazo.isoformat() if t.prazo else None,
             "hora": t.prazo_hora.strftime("%H:%M") if t.prazo_hora else None,
             "lista": nomes.get(t.projeto_id, "Caixa de Entrada"),
             "prioridade": NOME_PRIORIDADE.get(int(t.prioridade), "nenhuma")}
        if t.duracao_min:
            d["duracao_min"] = t.duracao_min
        if t.tags:
            d["etiquetas"] = t.tags
        if t.atrasada:
            d["atrasada"] = True
        if t.pai_id:
            d["pai_id"] = t.pai_id
        if t.concluida:
            d["concluida"] = True
        if t.notas and self.pedido.enviar_notas:
            d["notas"] = t.notas[:200]
        return d

    def _nomes_listas(self) -> dict:
        return {p.id: p.nome for p in self.banco.listar_projetos() + self.banco.listar_projetos_arquivados()}

    def _ler_listar_tarefas(self, filtro: str, limite: int = 40) -> dict:
        from .servico import AMANHA, CAIXA, CONCLUIDAS, HOJE, PROXIMOS, TODAS  # noqa: PLC0415
        f = (filtro or "").strip().lower()
        simples = {"hoje": HOJE, "amanha": AMANHA, "amanhã": AMANHA, "proximos": PROXIMOS, "próximos": PROXIMOS,
                   "todas": TODAS, "caixa": CAIXA, "concluidas": CONCLUIDAS, "concluídas": CONCLUIDAS}
        if f == "atrasadas":
            itens = [t for t in self.servico.listar(TODAS, self.hoje) if t.prazo and t.prazo < self.hoje]
        elif f in simples:
            itens = self.servico.listar(simples[f], self.hoje)
        else:
            proj = next((p for p in self.banco.listar_projetos() if p.nome.lower() == f), None)
            if proj is None:
                raise ValueError(f"filtro ou lista desconhecida: {filtro!r}")
            itens = self.servico.listar(proj.id, self.hoje)
        nomes = self._nomes_listas()
        limite = max(1, min(int(limite or 40), MAX_LISTAGEM))
        return {"total": len(itens), "tarefas": [self._tarefa_json(t, nomes) for t in itens[:limite]],
                "truncado": len(itens) > limite}

    def _ler_buscar_tarefas(self, texto: str) -> dict:
        achados = self.servico.buscar(texto)
        nomes = self._nomes_listas()
        return {"total": len(achados), "tarefas": [self._tarefa_json(t, nomes) for t in achados[:MAX_LISTAGEM]]}

    def _ler_ver_agenda(self, inicio: str, fim: str) -> dict:
        ini, fi = _data(inicio), _data(fim)
        if ini is None or fi is None or fi < ini:
            raise ValueError("informe inicio e fim válidos (AAAA-MM-DD)")
        fi = min(fi, ini + timedelta(days=30))
        dias = []
        for dia, ocs in self.servico.calendario.por_dia(ini, fi, incluir_finalizadas=False).items():
            if not ocs:
                continue
            dias.append({"data": dia.isoformat(), "dia_semana": DIAS_SEMANA[dia.weekday()], "itens": [
                {"titulo": o.titulo, "hora": o.hora.strftime("%H:%M") if o.hora else None,
                 "ate": o.fim_hora.strftime("%H:%M") if o.fim_hora else None,
                 "origem": "evento externo (Google ou link)" if o.externo else "tarefa",
                 **({"id": o.tarefa.id} if o.tarefa is not None else {})}
                for o in sorted(ocs, key=lambda o: (o.hora is not None, o.hora or time(0)))]})
        return {"dias": dias}

    def _ler_ver_listas(self) -> dict:
        c = self.servico.contagens(self.hoje)
        return {"listas": [{"nome": p.nome, "pasta": p.pasta or None, "tipo": p.tipo, "abertas": c.get(p.id, 0)}
                           for p in self.banco.listar_projetos()],
                "caixa_de_entrada": c.get("caixa", 0)}

    def _ler_ver_estatisticas(self) -> dict:
        est = self.servico.estatisticas
        r = est.resumo(self.hoje)
        dias = est.concluidas_por_dia(self.hoje - timedelta(days=13), self.hoje)
        por_hora: dict[int, int] = {}
        limite = self.hoje - timedelta(days=60)
        for t in self.banco.consultar("concluida_em IS NOT NULL AND apagada_em IS NULL"):
            dt = t.concluida_em if t.concluida_em.tzinfo else t.concluida_em.replace(tzinfo=tz.UTC)
            local = dt.astimezone(tz.tzlocal())
            if local.date() >= limite:
                por_hora[local.hour] = por_hora.get(local.hour, 0) + 1
        return {"pendentes": r.pendentes, "atrasadas": r.atrasadas, "concluidas_hoje": r.concluidas_hoje,
                "concluidas_na_semana": r.concluidas_semana, "sequencia_de_dias": r.sequencia_dias,
                "concluidas_por_dia_14d": {d.isoformat(): n for d, n in dias.items()},
                "por_lista": est.por_lista()[:6],
                "conclusoes_por_hora_60d": {f"{h:02d}h": n for h, n in sorted(por_hora.items())},
                "foco_na_semana_min": round(r.foco_semana_s / 60)}

    # ---- escrita: só vira proposta
    def _tarefa_existente(self, id_) -> object:
        t = self.banco.obter_tarefa(int(id_))
        if t is None or t.apagada_em is not None:
            raise ValueError(f"não existe tarefa com id {id_}")
        return t

    def _checar_lista(self, nome: str) -> None:
        if not nome:
            return
        achou = any(p.nome.lower() == nome.strip().lower() for p in self.banco.listar_projetos())
        if not achou and nome.strip().lower() not in self._listas_novas:
            raise ValueError(f"a lista {nome!r} não existe; proponha criar_lista antes")

    def _propor(self, nome: str, a: dict) -> str:
        if nome == "criar_tarefa":
            titulo = str(a.get("titulo") or "").strip()
            if not titulo:
                raise ValueError("falta o título")
            d, h = _data(a.get("data")), _hora(a.get("hora"))
            if h and not d:
                raise ValueError("hora sem data")
            self._checar_lista(a.get("lista") or "")
            if a.get("prioridade") and str(a["prioridade"]).lower() not in PRIORIDADES:
                raise ValueError("prioridade inválida")
            quando = f" em {_fmt_data(d)}" + (f" às {h:%H:%M}" if h else "") if d else ""
            lista = f" na lista {a['lista']}" if a.get("lista") else ""
            resumo = f"Criar “{titulo}”{quando}{lista}"
        elif nome == "atualizar_tarefa":
            t = self._tarefa_existente(a.get("id"))
            mud = []
            if "titulo" in a and str(a["titulo"]).strip() and a["titulo"] != t.titulo:
                mud.append(f"título para “{a['titulo']}”")
            if "data" in a:
                novo = _data(a["data"])
                mud.append(f"data de {_fmt_data(t.prazo)} para {_fmt_data(novo)}")
            if "hora" in a:
                novo_h = _hora(a["hora"])
                mud.append(f"hora de {_fmt_hora(t.prazo_hora)} para {_fmt_hora(novo_h)}")
            if "duracao_min" in a:
                mud.append(f"duração para {int(a['duracao_min'])} min")
            if "prioridade" in a:
                if str(a["prioridade"]).lower() not in PRIORIDADES:
                    raise ValueError("prioridade inválida")
                mud.append(f"prioridade para {a['prioridade']}")
            if "lista" in a:
                self._checar_lista(a.get("lista") or "")
                mud.append(f"lista para {a['lista'] or 'Caixa de Entrada'}")
            if "etiquetas" in a:
                mud.append("etiquetas")
            if "notas" in a:
                mud.append("notas")
            if not mud:
                raise ValueError("nada para mudar")
            resumo = f"Mudar “{t.titulo}”: " + "; ".join(mud)
        elif nome in ("concluir_tarefa", "apagar_tarefa"):
            t = self._tarefa_existente(a.get("id"))
            resumo = ("Concluir" if nome == "concluir_tarefa" else "Mandar para a lixeira") + f" “{t.titulo}”"
        elif nome == "criar_lista":
            n = str(a.get("nome") or "").strip()
            if not n:
                raise ValueError("falta o nome")
            self._listas_novas.add(n.lower())
            resumo = f"Criar a lista “{n}”"
        elif nome == "guardar_preferencia":
            txt = str(a.get("texto") or "").strip()
            if not txt:
                raise ValueError("falta o texto")
            resumo = f"Lembrar: {txt}"
        else:
            raise ValueError(f"ferramenta desconhecida: {nome}")
        self._plano.acoes.append(Acao(nome, dict(a), resumo))
        return f"Proposta registrada (ainda não aplicada): {resumo}"


# ---------------------------------------------------------------- aplicar e desfazer (thread da tela)
def _resolver_lista(servico, nome: str):
    if not nome:
        return None
    for p in servico.banco.listar_projetos():
        if p.nome.lower() == nome.strip().lower():
            return p.id
    raise ValueError(f"lista {nome!r} não encontrada")


def _aplicar_campos(servico, t, a: dict) -> None:
    if "titulo" in a and str(a["titulo"]).strip():
        t.titulo = str(a["titulo"]).strip()
    if "data" in a:
        t.prazo = _data(a["data"])
        if t.prazo is None:
            t.prazo_hora = None
    if "hora" in a:
        h = _hora(a["hora"])
        if h is not None and t.prazo is None:
            raise ValueError("hora sem data")
        t.prazo_hora = h
    if "duracao_min" in a:
        t.duracao_min = max(0, int(a["duracao_min"]))
    if a.get("prioridade"):
        t.prioridade = PRIORIDADES[str(a["prioridade"]).lower()]
    if "lista" in a:
        t.projeto_id = _resolver_lista(servico, a.get("lista") or "")
    if "etiquetas" in a:
        t.tags = [str(x).lstrip("#").strip() for x in (a.get("etiquetas") or []) if str(x).strip()]
    if "notas" in a:
        t.notas = str(a["notas"])


def aplicar_plano(servico, plano: Plano, config=None) -> Lote:
    """Executa as ações em ordem. Uma que falhe não impede as outras; o lote guarda como desfazer cada uma."""
    lote = Lote()
    for ac in plano.acoes:
        a = ac.args
        try:
            if ac.tipo == "criar_lista":
                p = servico.criar_projeto(str(a["nome"]).strip())
                lote.desfazer.append(("lista", p.id))
            elif ac.tipo == "criar_tarefa":
                t = Tarefa(titulo=str(a["titulo"]).strip(), ordem=servico.banco.proxima_ordem())
                _aplicar_campos(servico, t, a)
                proj = servico.banco.obter_projeto(t.projeto_id) if t.projeto_id is not None else None
                if proj is not None and proj.tipo == "notas":
                    t.tipo = "nota"
                servico.salvar(t)
                lote.desfazer.append(("apagar", t.id))
            elif ac.tipo == "atualizar_tarefa":
                antes = servico.banco.obter_tarefa(int(a["id"]))
                if antes is None:
                    raise ValueError("a tarefa não existe mais")
                t = servico.banco.obter_tarefa(int(a["id"]))
                _aplicar_campos(servico, t, a)
                servico.salvar(t)
                lote.desfazer.append(("restaurar_estado", antes))
            elif ac.tipo == "concluir_tarefa":
                antes = servico.banco.obter_tarefa(int(a["id"]))
                if antes is None:
                    raise ValueError("a tarefa não existe mais")
                if not antes.concluida:
                    servico.alternar_conclusao(antes.id)
                lote.desfazer.append(("restaurar_estado", antes))
            elif ac.tipo == "apagar_tarefa":
                servico.apagar(int(a["id"]))
                lote.desfazer.append(("restaurar", int(a["id"])))
            elif ac.tipo == "guardar_preferencia":
                if config is None:
                    raise ValueError("preferências indisponíveis")
                config.adicionar_preferencia(str(a["texto"]))
                lote.desfazer.append(("esquecer", str(a["texto"]).strip()))
            else:
                raise ValueError(f"ação desconhecida: {ac.tipo}")
            lote.resumos.append(ac.resumo)
        except (ValueError, KeyError, TypeError) as e:
            lote.erros.append(f"{ac.resumo}: {e}")
    return lote


def desfazer_lote(servico, lote: Lote, config=None) -> None:
    if lote.desfeito:
        return
    for passo in reversed(lote.desfazer):
        tipo, dado = passo
        if tipo == "apagar":
            servico.apagar(dado)
        elif tipo == "restaurar":
            servico.restaurar(dado)
        elif tipo == "restaurar_estado":
            servico.banco.salvar_tarefa(dado)
        elif tipo == "lista":
            servico.apagar_projeto(dado)
        elif tipo == "esquecer" and config is not None:
            config.definir_preferencias([p for p in config.preferencias if p != dado])
    lote.desfeito = True


# ---------------------------------------------------------------- conversas guardadas (só neste aparelho)
class Conversas:
    def __init__(self, banco):
        self.banco = banco

    def listar(self, limite: int = 30) -> list[dict]:
        return [dict(id=l["id"], titulo=l["titulo"] or "Conversa", atualizada_em=l["atualizada_em"])
                for l in self.banco.con.execute(
                    "SELECT id, titulo, atualizada_em FROM conversa_ia ORDER BY atualizada_em DESC LIMIT ?", (limite,))]

    def carregar(self, conversa_id: int) -> list[dict]:
        l = self.banco.con.execute("SELECT dados FROM conversa_ia WHERE id=?", (conversa_id,)).fetchone()
        return json.loads(l["dados"]) if l else []

    def salvar(self, conversa_id: int | None, historico: list[dict]) -> int:
        agora = agora_utc().isoformat()
        leve = []
        for m in historico:                 # guarda só a conversa: texto da pessoa e respostas finais
            if m["papel"] == "usuario":
                if m.get("anexos"):         # imagens e PDFs não vão para o banco: só o nome do arquivo
                    m = {**m, "anexos": descricao_para_guardar(m["anexos"])}
                leve.append(m)
            elif m["papel"] == "assistente" and m.get("texto") and not m.get("chamadas"):
                leve.append(m)
        dados = json.dumps(leve, ensure_ascii=False)
        if conversa_id is None:
            primeiro = next((m["texto"] for m in historico if m["papel"] == "usuario"), "")
            cur = self.banco.con.execute(
                "INSERT INTO conversa_ia(titulo, criada_em, atualizada_em, dados) VALUES (?,?,?,?)",
                (primeiro.strip()[:60], agora, agora, dados))
            conversa_id = cur.lastrowid
        else:
            self.banco.con.execute("UPDATE conversa_ia SET atualizada_em=?, dados=? WHERE id=?",
                                   (agora, dados, conversa_id))
        self.banco.con.commit()
        return conversa_id

    def apagar(self, conversa_id: int) -> None:
        self.banco.con.execute("DELETE FROM conversa_ia WHERE id=?", (conversa_id,))
        self.banco.con.commit()


def turno_em_arquivo(caminho: str, pasta_dados, pedido: Pedido, historico: list[dict], texto: str,
                     transporte=transporte_http, anexos: list[dict] | None = None) -> Turno:
    """Roda um turno numa conexão própria do banco (para usar numa thread sem travar a tela)."""
    from .db import Banco  # noqa: PLC0415
    from .servico import Servico  # noqa: PLC0415
    servico = Servico(Banco(caminho), pasta_dados=pasta_dados)
    try:
        return Assistente(servico, pedido, transporte).turno(historico, texto, anexos)
    finally:
        servico.banco.fechar()
