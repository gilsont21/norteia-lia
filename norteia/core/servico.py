"""Regras de negócio: criação rápida, listas inteligentes, conclusão, repetição, lembretes,
gestão de projetos e etiquetas."""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from dateutil.relativedelta import relativedelta

from . import filtros as filtros_core
from . import recorrencia
from .db import Banco
from .lembretes import HORA_PADRAO, Lembrete, instante_do_lembrete
from .models import Filtro, Prioridade, Projeto, Tag, Tarefa, agora_utc

# Listas inteligentes (chaves usadas pela interface)
HOJE, AMANHA, PROXIMOS, TODAS = "hoje", "amanha", "proximos", "todas"
CONCLUIDAS, LIXEIRA = "concluidas", "lixeira"
CAIXA = "caixa"            # tarefas sem projeto
PREFIXO_TAG = "tag:"       # chave de lista de etiqueta: "tag:casa"
PREFIXO_FILTRO = "filtro:"  # chave de filtro salvo: "filtro:3"

MAX_NIVEIS = 5             # profundidade máxima das subtarefas
LIMITE_INSISTENCIA = timedelta(hours=24)   # o lembrete constante para depois disso


def chave_tag(nome: str) -> str:
    return PREFIXO_TAG + nome


def chave_filtro(filtro_id: int) -> str:
    return PREFIXO_FILTRO + str(filtro_id)


def _normalizar_tag(nome: str) -> str:
    return nome.strip().lstrip("#").lower()


_DIAS_SEMANA = {
    "seg": 0, "segunda": 0, "ter": 1, "terca": 1, "terça": 1, "qua": 2, "quarta": 2,
    "qui": 3, "quinta": 3, "sex": 4, "sexta": 4, "sab": 5, "sábado": 5, "sabado": 5,
    "dom": 6, "domingo": 6,
}

_RE_HORA = re.compile(r"(?:\bàs\s+|\bas\s+|@)(\d{1,2})(?:[:h](\d{2}))?h?\b", re.IGNORECASE)
_REPETICOES = [
    (re.compile(r"\b(?:todo\s+dia|diariamente|todos\s+os\s+dias)\b", re.I), "FREQ=DAILY"),
    (re.compile(r"\bdias\s+[úu]teis\b", re.I), recorrencia.DIAS_UTEIS),
    (re.compile(r"\b(?:toda\s+semana|semanalmente)\b", re.I), "FREQ=WEEKLY"),
    (re.compile(r"\b(?:todo\s+m[êe]s|mensalmente)\b", re.I), "FREQ=MONTHLY"),
    (re.compile(r"\b(?:todo\s+ano|anualmente)\b", re.I), "FREQ=YEARLY"),
]

# datas por extenso (testadas na ordem; a primeira que casar vale)
_RE_DEPOIS_AMANHA = re.compile(r"\bdepois\s+de\s+amanh[ãa]\b", re.I)
_RE_DAQUI = re.compile(r"\b(?:daqui\s+a|em)\s+(\d{1,3})\s+(dias?|semanas?|m[êe]s(?:es)?|anos?)\b", re.I)
_RE_SEMANA_QUE_VEM = re.compile(r"\b(?:(?:na\s+)?semana\s+que\s+vem|pr[óo]xima\s+semana)\b", re.I)
_RE_MES_QUE_VEM = re.compile(r"\b(?:(?:no\s+)?m[êe]s\s+que\s+vem|pr[óo]ximo\s+m[êe]s)\b", re.I)
_RE_DATA_NUMERICA = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b")
_RE_DIA_DO_MES = re.compile(r"\bdia\s+(\d{1,2})\b", re.I)


def _proximo_dia_do_mes(dia: int, hoje: date) -> date | None:
    """Próxima data (hoje ou depois) com esse dia do mês; pula meses em que o dia não existe."""
    ano, mes = hoje.year, hoje.month
    for _ in range(14):
        if dia <= calendar.monthrange(ano, mes)[1]:
            candidata = date(ano, mes, dia)
            if candidata >= hoje:
                return candidata
        mes += 1
        if mes > 12:
            ano, mes = ano + 1, 1
    return None


def _data_livre(texto: str, hoje: date) -> tuple[date | None, str]:
    """Procura uma data escrita por extenso. Devolve (data, texto sem o trecho)."""
    m = _RE_DEPOIS_AMANHA.search(texto)
    if m:
        return hoje + timedelta(days=2), texto.replace(m.group(0), "", 1)
    m = _RE_DAQUI.search(texto)
    if m:
        n, unidade = int(m.group(1)), m.group(2).lower()
        if unidade.startswith("dia"):
            data = hoje + timedelta(days=n)
        elif unidade.startswith("semana"):
            data = hoje + timedelta(weeks=n)
        elif unidade.startswith("m"):
            data = hoje + relativedelta(months=n)
        else:
            data = hoje + relativedelta(years=n)
        return data, texto.replace(m.group(0), "", 1)
    m = _RE_SEMANA_QUE_VEM.search(texto)
    if m:
        return hoje + timedelta(days=7), texto.replace(m.group(0), "", 1)
    m = _RE_MES_QUE_VEM.search(texto)
    if m:
        return hoje + relativedelta(months=1), texto.replace(m.group(0), "", 1)
    m = _RE_DATA_NUMERICA.search(texto)
    if m:
        dia, mes = int(m.group(1)), int(m.group(2))
        try:
            if m.group(3):
                data = date(int(m.group(3)), mes, dia)
            else:
                data = date(hoje.year, mes, dia)
                if data < hoje:
                    data = date(hoje.year + 1, mes, dia)
            return data, texto.replace(m.group(0), "", 1)
        except ValueError:
            pass  # 31/02 e parecidos: deixa no título
    m = _RE_DIA_DO_MES.search(texto)
    if m and 1 <= int(m.group(1)) <= 31:
        data = _proximo_dia_do_mes(int(m.group(1)), hoje)
        if data:
            return data, texto.replace(m.group(0), "", 1)
    return None, texto


@dataclass
class EntradaRapida:
    titulo: str
    prazo: date | None = None
    prazo_hora: time | None = None
    repeticao: str | None = None
    lembretes: list[int] = field(default_factory=list)
    prioridade: Prioridade = Prioridade.NENHUMA
    tags: list[str] = field(default_factory=list)
    projeto: str | None = None       # nome escrito depois de "~"


def interpretar(texto: str, hoje: date | None = None) -> EntradaRapida:
    """Entende atalhos: 'hoje', 'amanhã', 'depois de amanhã', 'daqui a 3 dias', 'semana que vem',
    'dia 15', '15/11', dia da semana, 'às 14h', 'todo dia', !1 a !3, #etiqueta e ~lista."""
    hoje = hoje or date.today()
    prazo = None
    hora = None
    repeticao = None
    prioridade = Prioridade.NENHUMA
    tags = re.findall(r"#([\wÀ-ÿ-]+)", texto)
    resto = re.sub(r"#[\wÀ-ÿ-]+", "", texto)

    projeto = None
    m = re.search(r"~([\wÀ-ÿ-]+)", resto)
    if m:
        projeto = m.group(1).replace("_", " ")
        resto = resto.replace(m.group(0), "", 1)

    m = re.search(r"!([1-3])", resto)
    if m:
        prioridade = Prioridade(int(m.group(1)))
        resto = resto.replace(m.group(0), "")

    for padrao, regra in _REPETICOES:
        if padrao.search(resto):
            repeticao = regra
            resto = padrao.sub("", resto, count=1)
            break

    m = _RE_HORA.search(resto)
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if h < 24 and mi < 60:
            hora = time(h, mi)
            resto = resto.replace(m.group(0), "", 1)

    prazo, resto = _data_livre(resto, hoje)

    saida = []
    for palavra in resto.split():
        chave = palavra.lower().strip(",.")
        if prazo is None and chave == "hoje":
            prazo = hoje
        elif prazo is None and chave in ("amanhã", "amanha"):
            prazo = hoje + timedelta(days=1)
        elif prazo is None and chave in _DIAS_SEMANA:
            falta = (_DIAS_SEMANA[chave] - hoje.weekday()) % 7 or 7
            prazo = hoje + timedelta(days=falta)
        else:
            saida.append(palavra)
    if prazo is None and (hora or repeticao):
        prazo = hoje
    titulo = " ".join(saida).strip() or texto.strip()
    return EntradaRapida(titulo, prazo, hora, repeticao, [0] if hora else [], prioridade, tags, projeto)


@dataclass
class ResumoDia:
    hoje: int
    atrasadas: int
    titulos: list[str]

    @property
    def texto(self) -> str:
        partes = []
        if self.hoje:
            partes.append(f"{self.hoje} tarefa{'s' if self.hoje != 1 else ''} para hoje")
        if self.atrasadas:
            partes.append(f"{self.atrasadas} atrasada{'s' if self.atrasadas != 1 else ''}")
        return "Você tem " + " e ".join(partes) + "."


_ATIVAS = "apagada_em IS NULL AND concluida_em IS NULL AND descartada_em IS NULL AND pai_id IS NULL"
# tarefas de listas arquivadas ou apagadas não aparecem nas listas inteligentes
_VISIVEL = ("(projeto_id IS NULL OR projeto_id IN "
            "(SELECT id FROM projeto WHERE arquivado = 0 AND apagado_em IS NULL))")


class Servico:
    def __init__(self, banco: Banco, pasta_dados=None):
        """`pasta_dados` é onde ficam os anexos (None = anexos desligados)."""
        self.banco = banco
        self.pasta_dados = pasta_dados
        self._extras: dict = {}

    def _extra(self, nome: str, fabrica):
        if nome not in self._extras:
            self._extras[nome] = fabrica()
        return self._extras[nome]

    # ---- módulos auxiliares (criados só quando usados) ----
    @property
    def calendario(self):
        from .calendario import Calendario
        return self._extra("calendario", lambda: Calendario(self))

    @property
    def habitos(self):
        from .habitos import Habitos
        return self._extra("habitos", lambda: Habitos(self.banco))

    @property
    def foco(self):
        from .foco import Foco
        return self._extra("foco", lambda: Foco(self.banco))

    @property
    def contagens_regressivas(self):
        from .contagens import Contagens
        return self._extra("contagens", lambda: Contagens(self.banco))

    @property
    def comentarios(self):
        from .comentarios import Comentarios
        return self._extra("comentarios", lambda: Comentarios(self))

    @property
    def modelos(self):
        from .modelos import Modelos
        return self._extra("modelos", lambda: Modelos(self))

    @property
    def anexos(self):
        from .anexos import Anexos
        return self._extra("anexos", lambda: Anexos(self, self.pasta_dados))

    @property
    def matriz(self):
        from .matriz import Matriz
        return self._extra("matriz", lambda: Matriz(self))

    @property
    def estatisticas(self):
        from .estatisticas import Estatisticas
        return self._extra("estatisticas", lambda: Estatisticas(self))

    @property
    def assin(self):
        from .assinaturas import Assinaturas
        return self._extra("assin", lambda: Assinaturas(self.banco))

    def assinaturas(self, origem: str | None = None) -> list[dict]:
        return self.assin.listar(origem)

    @property
    def ia(self):
        from .ia_provedores import ConfigIA
        return self._extra("ia", lambda: ConfigIA(self.banco))

    @property
    def conversas_ia(self):
        from .assistente import Conversas
        return self._extra("conversas_ia", lambda: Conversas(self.banco))

    @property
    def google(self):
        from .google_agenda import Google
        return self._extra("google", lambda: Google(self))

    # ---- criação e edição ----
    def _projeto_por_nome(self, nome: str) -> Projeto | None:
        nome = nome.strip().lower()
        todos = self.banco.listar_projetos()
        for p in todos:
            if p.nome.lower() == nome:
                return p
        for p in todos:
            if p.nome.lower().startswith(nome):
                return p
        return None

    def adicionar_rapido(self, texto: str, projeto_id: int | None = None) -> Tarefa:
        e = interpretar(texto)
        if e.projeto:
            achado = self._projeto_por_nome(e.projeto)
            if achado:
                projeto_id = achado.id
            else:  # nome desconhecido: não perde o texto, vira parte do título
                e.titulo = f"{e.titulo} ~{e.projeto}".strip()
        t = Tarefa(
            titulo=e.titulo,
            projeto_id=projeto_id,
            prazo=e.prazo,
            prazo_hora=e.prazo_hora,
            repeticao=e.repeticao,
            lembretes=list(e.lembretes),
            prioridade=e.prioridade,
            tags=list(e.tags),
            ordem=self.banco.proxima_ordem(),
        )
        proj = self.banco.obter_projeto(projeto_id) if projeto_id is not None else None
        if proj is not None and proj.tipo == "notas":
            t.tipo = "nota"                          # lista de notas: itens sem caixinha de conclusão
        return self.banco.salvar_tarefa(t)

    def salvar(self, t: Tarefa) -> Tarefa:
        if t.prazo is None:
            t.inicio = None                          # sem fim não há período
        elif t.inicio is not None:
            if t.inicio == t.prazo:
                t.inicio = None
            elif t.inicio > t.prazo:                 # início depois do fim: troca
                t.inicio, t.prazo = t.prazo, t.inicio
        return self.banco.salvar_tarefa(t)

    def criar_nota(self, titulo: str, projeto_id: int | None = None) -> Tarefa:
        """Nota: item sem caixinha de conclusão, para ideias e anotações."""
        titulo = titulo.strip()
        if not titulo:
            raise ValueError("a nota precisa de um título")
        return self.banco.salvar_tarefa(Tarefa(titulo=titulo, projeto_id=projeto_id, tipo="nota",
                                                ordem=self.banco.proxima_ordem()))

    def _criar_proxima_ocorrencia(self, t: Tarefa, hoje: date | None) -> None:
        if t.repeticao and t.prazo:
            regra = recorrencia.decrementar_contagem(t.repeticao)      # "5 vezes": a próxima tem 4
            seguinte = recorrencia.proxima(t.repeticao, t.prazo, hoje) if regra else None
            if seguinte:
                self.banco.salvar_tarefa(Tarefa(
                    titulo=t.titulo, notas=t.notas, projeto_id=t.projeto_id,
                    prioridade=t.prioridade, prazo=seguinte, prazo_hora=t.prazo_hora,
                    repeticao=regra, lembretes=list(t.lembretes), tags=list(t.tags),
                    ordem=t.ordem, fixada=t.fixada, insistir_min=t.insistir_min,
                    inicio=(seguinte - (t.prazo - t.inicio)) if t.inicio else None,
                    duracao_min=t.duracao_min, secao=t.secao, tipo=t.tipo,
                ))

    def alternar_conclusao(self, tarefa_id: int, hoje: date | None = None) -> Tarefa:
        """Conclui ou reabre. Concluir uma tarefa que se repete cria a próxima ocorrência.
        Numa tarefa marcada como "não será feito", reabre."""
        t = self.banco.obter_tarefa(tarefa_id)
        if t.eh_nota:
            return t                                  # nota não se conclui
        if t.concluida or t.descartada:
            t.concluida_em = None
            t.descartada_em = None
            return self.banco.salvar_tarefa(t)
        t.concluida_em = agora_utc()
        self.banco.salvar_tarefa(t)
        self.banco.limpar_soneca(t.id)
        self._criar_proxima_ocorrencia(t, hoje)
        return t

    def alternar_descarte(self, tarefa_id: int, hoje: date | None = None) -> Tarefa:
        """Marca ou desmarca "não será feito". Numa tarefa repetida, a próxima ocorrência é criada."""
        t = self.banco.obter_tarefa(tarefa_id)
        if t.descartada:
            t.descartada_em = None
            return self.banco.salvar_tarefa(t)
        t.concluida_em = None
        t.descartada_em = agora_utc()
        self.banco.salvar_tarefa(t)
        self.banco.limpar_soneca(t.id)
        self._criar_proxima_ocorrencia(t, hoje)
        return t

    def alternar_fixada(self, tarefa_id: int) -> Tarefa:
        t = self.banco.obter_tarefa(tarefa_id)
        t.fixada = not t.fixada
        return self.banco.salvar_tarefa(t)

    def duplicar(self, tarefa_id: int) -> Tarefa:
        """Cópia da tarefa (e das subtarefas), sem conclusão, fixação nem lixeira."""
        original = self.banco.obter_tarefa(tarefa_id)
        if original is None:
            raise ValueError("tarefa não encontrada")
        return self._copiar(original, original.pai_id)

    def _copiar(self, origem: Tarefa, novo_pai_id: int | None) -> Tarefa:
        copia = self.banco.salvar_tarefa(Tarefa(
            titulo=origem.titulo, notas=origem.notas, projeto_id=origem.projeto_id, pai_id=novo_pai_id,
            prioridade=origem.prioridade, prazo=origem.prazo, prazo_hora=origem.prazo_hora,
            repeticao=origem.repeticao, lembretes=list(origem.lembretes), tags=list(origem.tags),
            ordem=self.banco.proxima_ordem(), insistir_min=origem.insistir_min, inicio=origem.inicio,
            duracao_min=origem.duracao_min, secao=origem.secao, tipo=origem.tipo))
        for sub in self.subtarefas(origem.id):
            self._copiar(sub, copia.id)
        return copia

    def apagar(self, tarefa_id: int) -> None:
        """Manda para a lixeira, junto com todas as subtarefas."""
        t = self.banco.obter_tarefa(tarefa_id)
        agora = agora_utc()
        t.apagada_em = agora
        self.banco.salvar_tarefa(t)
        self.banco.limpar_soneca(tarefa_id)
        for sub in self.descendentes(tarefa_id):
            if sub.apagada_em is None:
                sub.apagada_em = agora
                self.banco.salvar_tarefa(sub)

    def restaurar(self, tarefa_id: int) -> None:
        t = self.banco.obter_tarefa(tarefa_id)
        instante = t.apagada_em
        t.apagada_em = None
        if t.projeto_id:
            proj = self.banco.obter_projeto(t.projeto_id)
            if proj is None or proj.apagado_em is not None:
                t.projeto_id = None  # a lista foi apagada: volta para a Caixa de entrada
        self.banco.salvar_tarefa(t)
        for sub in self.descendentes(tarefa_id):
            if sub.apagada_em == instante:  # só as que foram apagadas junto com a tarefa
                sub.apagada_em = None
                self.banco.salvar_tarefa(sub)

    # ---- subtarefas (checklist, vários níveis) ----
    def subtarefas(self, pai_id: int, incluir_apagadas: bool = False) -> list[Tarefa]:
        filtro = "pai_id = ?" + ("" if incluir_apagadas else " AND apagada_em IS NULL")
        return self.banco.consultar(filtro, (pai_id,), "ordem, id")

    def nivel(self, tarefa_id: int) -> int:
        """0 para tarefa principal, 1 para subtarefa, 2 para sub-subtarefa..."""
        nivel, atual = 0, self.banco.obter_tarefa(tarefa_id)
        while atual is not None and atual.pai_id is not None:
            nivel += 1
            atual = self.banco.obter_tarefa(atual.pai_id)
        return nivel

    def descendentes(self, pai_id: int) -> list[Tarefa]:
        """Todas as subtarefas, de qualquer nível (inclui as apagadas)."""
        saida, fila = [], [pai_id]
        while fila:
            for sub in self.subtarefas(fila.pop(0), incluir_apagadas=True):
                saida.append(sub)
                fila.append(sub.id)
        return saida

    def arvore(self, pai_id: int) -> list[tuple[Tarefa, int]]:
        """[(subtarefa, nível)] em profundidade, na ordem de exibição (nível 1 = filhas diretas)."""
        saida: list[tuple[Tarefa, int]] = []

        def descer(id_: int, nivel: int) -> None:
            for sub in self.subtarefas(id_):
                saida.append((sub, nivel))
                descer(sub.id, nivel + 1)
        descer(pai_id, 1)
        return saida

    def adicionar_subtarefa(self, pai_id: int, titulo: str) -> Tarefa:
        pai = self.banco.obter_tarefa(pai_id)
        titulo = titulo.strip()
        if pai is None or not titulo:
            raise ValueError("subtarefa precisa de uma tarefa principal e de um título")
        if self.nivel(pai_id) + 1 >= MAX_NIVEIS:
            raise ValueError(f"no máximo {MAX_NIVEIS} níveis de subtarefas")
        return self.banco.salvar_tarefa(Tarefa(
            titulo=titulo, projeto_id=pai.projeto_id, pai_id=pai_id,
            ordem=self.banco.proxima_ordem()))

    def progresso(self, pai_id: int) -> tuple[int, int]:
        """(feitas, total) das subtarefas diretas."""
        subs = self.subtarefas(pai_id)
        return sum(1 for s in subs if s.concluida), len(subs)

    def progressos(self) -> dict[int, tuple[int, int]]:
        """{id da tarefa: (feitas, total)} para todas as que têm subtarefas."""
        linhas = self.banco.con.execute(
            "SELECT pai_id, SUM(concluida_em IS NOT NULL) AS feitas, COUNT(*) AS total "
            "FROM tarefa WHERE pai_id IS NOT NULL AND apagada_em IS NULL GROUP BY pai_id")
        return {l["pai_id"]: (int(l["feitas"]), int(l["total"])) for l in linhas}

    # ---- ordem manual ----
    def reordenar(self, ids_na_ordem: list[int]) -> None:
        """Grava a ordem escolhida arrastando: a posição na lista vira o número de ordem."""
        for posicao, tarefa_id in enumerate(ids_na_ordem):
            t = self.banco.obter_tarefa(tarefa_id)
            if t is not None and t.ordem != posicao:
                t.ordem = posicao
                self.banco.salvar_tarefa(t)

    # ---- filtros salvos ----
    def criar_filtro(self, nome: str, criterios: dict) -> Filtro:
        return self.banco.salvar_filtro(Filtro(nome.strip(), dict(criterios)))

    def apagar_filtro(self, filtro_id: int) -> None:
        f = self.banco.obter_filtro(filtro_id)
        if f:
            f.apagado_em = agora_utc()
            self.banco.salvar_filtro(f)

    def renomear_filtro(self, filtro_id: int, nome: str) -> None:
        f = self.banco.obter_filtro(filtro_id)
        if f and nome.strip():
            f.nome = nome.strip()
            self.banco.salvar_filtro(f)

    # ---- projetos (listas) ----
    VISOES_LISTA = ("lista", "kanban", "linha_tempo")

    def criar_projeto(self, nome: str, cor: str = "#c39a3f", *, emoji: str = "", visao: str = "lista",
                      pasta: str = "", tipo: str = "tarefas", inteligente: str = "todas") -> Projeto:
        ordem = len(self.banco.listar_projetos())
        return self.banco.salvar_projeto(Projeto(
            nome, cor, ordem, pasta=pasta.strip(), emoji=emoji.strip(),
            visao=visao if visao in self.VISOES_LISTA else "lista",
            tipo="notas" if tipo == "notas" else "tarefas",
            inteligente="nenhuma" if inteligente == "nenhuma" else "todas"))

    def atualizar_projeto(self, projeto_id: int, **campos) -> Projeto:
        """Muda nome, cor, emoji, visão, pasta, tipo e lista inteligente de uma lista (só o que for passado)."""
        p = self.banco.obter_projeto(projeto_id)
        if p is None:
            raise ValueError("projeto inexistente")
        if "nome" in campos:
            nome = str(campos["nome"]).strip()
            if not nome:
                raise ValueError("a lista precisa de um nome")
            p.nome = nome
        if "cor" in campos and campos["cor"]:
            p.cor = campos["cor"]
        if "emoji" in campos:
            p.emoji = str(campos["emoji"]).strip()
        if campos.get("visao") in self.VISOES_LISTA:
            p.visao = campos["visao"]
        if "pasta" in campos:
            p.pasta = str(campos["pasta"]).strip()
        if "tipo" in campos:
            p.tipo = "notas" if campos["tipo"] == "notas" else "tarefas"
        if "inteligente" in campos:
            p.inteligente = "nenhuma" if campos["inteligente"] == "nenhuma" else "todas"
        return self.banco.salvar_projeto(p)

    def definir_visao_projeto(self, projeto_id: int, visao: str) -> Projeto | None:
        p = self.banco.obter_projeto(projeto_id)
        if p is None or visao not in self.VISOES_LISTA or p.visao == visao:
            return p
        p.visao = visao
        return self.banco.salvar_projeto(p)

    def renomear_projeto(self, projeto_id: int, nome: str) -> Projeto:
        p = self.banco.obter_projeto(projeto_id)
        nome = nome.strip()
        if p is None or not nome:
            raise ValueError("projeto inexistente ou nome vazio")
        p.nome = nome
        return self.banco.salvar_projeto(p)

    def definir_cor_projeto(self, projeto_id: int, cor: str) -> Projeto:
        p = self.banco.obter_projeto(projeto_id)
        if p is None:
            raise ValueError("projeto inexistente")
        p.cor = cor
        return self.banco.salvar_projeto(p)

    def definir_pasta_projeto(self, projeto_id: int, pasta: str) -> Projeto:
        """Agrupa a lista numa pasta da barra lateral ("" tira da pasta)."""
        p = self.banco.obter_projeto(projeto_id)
        if p is None:
            raise ValueError("projeto inexistente")
        p.pasta = pasta.strip()
        return self.banco.salvar_projeto(p)

    def arquivar_projeto(self, projeto_id: int, arquivar: bool = True) -> Projeto:
        p = self.banco.obter_projeto(projeto_id)
        if p is None:
            raise ValueError("projeto inexistente")
        p.arquivado = arquivar
        return self.banco.salvar_projeto(p)

    def apagar_projeto(self, projeto_id: int) -> None:
        """Apaga a lista e manda as tarefas dela para a lixeira (como o original)."""
        p = self.banco.obter_projeto(projeto_id)
        if p is None or p.apagado_em is not None:
            return
        agora = agora_utc()
        p.apagado_em = agora
        self.banco.salvar_projeto(p)
        for t in self.banco.consultar("projeto_id = ? AND apagada_em IS NULL", (projeto_id,)):
            t.apagada_em = agora
            self.banco.salvar_tarefa(t)
            self.banco.limpar_soneca(t.id)

    def restaurar_projeto(self, projeto_id: int) -> None:
        p = self.banco.obter_projeto(projeto_id)
        if p is None or p.apagado_em is None:
            return
        instante = p.apagado_em
        p.apagado_em = None
        self.banco.salvar_projeto(p)
        for t in self.banco.consultar("projeto_id = ? AND apagada_em IS NOT NULL", (projeto_id,)):
            if t.apagada_em == instante:
                t.apagada_em = None
                self.banco.salvar_tarefa(t)

    def reordenar_projetos(self, ids_na_ordem: list[int]) -> None:
        for posicao, projeto_id in enumerate(ids_na_ordem):
            p = self.banco.obter_projeto(projeto_id)
            if p is not None and p.ordem != posicao:
                p.ordem = posicao
                self.banco.salvar_projeto(p)

    # ---- etiquetas ----
    def criar_tag(self, nome: str) -> Tag:
        nome = _normalizar_tag(nome)
        if not nome or " " in nome:
            raise ValueError("a etiqueta precisa de um nome sem espaços")
        return self.banco.obter_ou_criar_tag(nome)

    def definir_cor_tag(self, nome: str, cor: str) -> Tag:
        tag = self.banco.obter_tag(nome)
        if tag is None:
            raise ValueError("etiqueta inexistente")
        tag.cor = cor
        return self.banco.salvar_tag(tag)

    def renomear_tag(self, antigo: str, novo: str) -> None:
        """Renomeia. Se já existe uma etiqueta com o novo nome, as duas se fundem."""
        antigo, novo = _normalizar_tag(antigo), _normalizar_tag(novo)
        if not novo:
            raise ValueError("o nome da etiqueta não pode ficar vazio")
        if antigo == novo:
            return
        origem = self.banco.obter_tag(antigo)
        if origem is None:
            return
        if self.banco.obter_tag(novo) is not None:
            self.mesclar_tags(antigo, novo)
            return
        afetadas = self.banco.tarefas_da_tag(antigo)
        origem.nome = novo
        self.banco.salvar_tag(origem)
        for t in afetadas:  # regrava para o carimbo mudar e a sincronização levar a novidade
            t.tags = [novo if g == antigo else g for g in t.tags]
            self.banco.salvar_tarefa(t)

    def mesclar_tags(self, origem: str, destino: str) -> None:
        origem, destino = _normalizar_tag(origem), _normalizar_tag(destino)
        if origem == destino:
            return
        tag_origem = self.banco.obter_tag(origem)
        if tag_origem is None:
            return
        self.banco.obter_ou_criar_tag(destino)
        for t in self.banco.tarefas_da_tag(origem):
            t.tags = sorted({destino if g == origem else g for g in t.tags})
            self.banco.salvar_tarefa(t)
        self.banco.excluir_tag(tag_origem.id)

    def apagar_tag(self, nome: str) -> None:
        nome = _normalizar_tag(nome)
        tag = self.banco.obter_tag(nome)
        if tag is None:
            return
        for t in self.banco.tarefas_da_tag(nome):
            t.tags = [g for g in t.tags if g != nome]
            self.banco.salvar_tarefa(t)
        self.banco.excluir_tag(tag.id)

    # ---- lembretes ----
    def _instantes(self, t: Tarefa, minutos: int, agora: datetime) -> list[datetime]:
        """Momentos em que esse lembrete já deveria ter tocado (vários, se for lembrete constante).

        O lembrete constante vale só para o lembrete mais próximo do prazo e para depois de
        `LIMITE_INSISTENCIA`."""
        base = instante_do_lembrete(t, minutos)
        if base is None:
            return []
        if t.insistir_min <= 0 or minutos != min(t.lembretes):
            return [base] if base <= agora else []
        passo = timedelta(minutes=t.insistir_min)
        saida, i = [], base
        while i <= agora and i - base <= LIMITE_INSISTENCIA:
            saida.append(i)
            i += passo
        return saida

    def lembretes_vencidos(
        self, agora: datetime | None = None, janela: timedelta = timedelta(hours=12)
    ) -> list[Lembrete]:
        """Lembretes que já deveriam ter tocado e ainda não foram avisados.

        `agora` é hora local. Lembretes mais antigos que a janela são ignorados, para não
        despejar notificações velhas quando o app abre depois de muito tempo. Lembretes
        adiados (soneca) voltam quando o tempo escolhido acaba."""
        agora = agora or datetime.now()
        candidatas = self.banco.consultar(
            "apagada_em IS NULL AND concluida_em IS NULL AND descartada_em IS NULL "
            "AND prazo IS NOT NULL AND lembretes != '[]'"
        )
        saida: list[Lembrete] = []
        for t in candidatas:
            for minutos in t.lembretes:
                pendentes = [i for i in self._instantes(t, minutos, agora)
                             if not self.banco.ja_notificada(t.id, i)]
                if pendentes and agora - pendentes[-1] <= janela:
                    saida.append(Lembrete(t, pendentes[-1], minutos))
        for tarefa_id, ate in self.banco.sonecas():
            if ate > agora:
                continue
            t = self.banco.obter_tarefa(tarefa_id)
            if t is None or t.apagada_em or t.finalizada:
                self.banco.limpar_soneca(tarefa_id)
            else:
                saida.append(Lembrete(t, ate, -1))
        return sorted(saida, key=lambda l: l.instante)

    def marcar_avisado(self, lembrete: Lembrete) -> None:
        if lembrete.adiado:
            self.banco.limpar_soneca(lembrete.tarefa.id)
            return
        for i in self._instantes(lembrete.tarefa, lembrete.minutos_antes, lembrete.instante):
            self.banco.marcar_notificada(lembrete.tarefa.id, i)

    def adiar(self, tarefa_id: int, minutos: int, agora: datetime | None = None) -> datetime:
        """Soneca: o lembrete volta daqui a `minutos`. Vale só neste aparelho."""
        ate = (agora or datetime.now()) + timedelta(minutes=minutos)
        self.banco.definir_soneca(tarefa_id, ate)
        return ate

    def adiar_para_amanha(self, tarefa_id: int, agora: datetime | None = None) -> datetime:
        agora = agora or datetime.now()
        ate = datetime.combine(agora.date() + timedelta(days=1), HORA_PADRAO)
        self.banco.definir_soneca(tarefa_id, ate)
        return ate

    def resumo_diario(self, agora: datetime | None = None, hora: time = time(8, 0)) -> ResumoDia | None:
        """Resumo do dia, uma vez por dia, a partir da `hora`. None se não há nada a avisar."""
        agora = agora or datetime.now()
        hoje = agora.date()
        if agora.time() < hora or self.banco.meta("resumo_enviado") == hoje.isoformat():
            return None
        self.banco.definir_meta("resumo_enviado", hoje.isoformat())
        ativas = self.listar(HOJE, hoje)
        atrasadas = [t for t in ativas if t.prazo < hoje]
        do_dia = [t for t in ativas if t.prazo == hoje]
        if not ativas:
            return None
        return ResumoDia(len(do_dia), len(atrasadas), [t.titulo for t in ativas][:5])

    # ---- listas ----
    def listar(self, lista: str | int, hoje: date | None = None) -> list[Tarefa]:
        hoje = hoje or date.today()
        h = hoje.isoformat()
        ordem = ("fixada DESC, prazo IS NULL, prazo, prazo_hora IS NULL, prazo_hora, "
                 "prioridade DESC, ordem, id")
        ativas = f"{_ATIVAS} AND {_VISIVEL}"
        inteligentes = (f"{ativas} AND (projeto_id IS NULL OR projeto_id NOT IN "
                        "(SELECT id FROM projeto WHERE inteligente = 'nenhuma'))")
        if lista == LIXEIRA:
            return self.banco.consultar("apagada_em IS NOT NULL", ordem="apagada_em DESC")
        if lista == CONCLUIDAS:
            return self.banco.consultar(
                "(concluida_em IS NOT NULL OR descartada_em IS NOT NULL) AND apagada_em IS NULL "
                "AND pai_id IS NULL AND " + _VISIVEL,
                ordem="COALESCE(concluida_em, descartada_em) DESC",
            )
        if lista == HOJE:
            return self.banco.consultar(f"{inteligentes} AND prazo IS NOT NULL AND prazo <= ?", (h,), ordem)
        if lista == AMANHA:
            amanha = (hoje + timedelta(days=1)).isoformat()
            return self.banco.consultar(f"{inteligentes} AND prazo = ?", (amanha,), ordem)
        if lista == PROXIMOS:
            fim = (hoje + timedelta(days=7)).isoformat()
            return self.banco.consultar(f"{inteligentes} AND prazo IS NOT NULL AND prazo <= ?", (fim,), ordem)
        if lista == TODAS:
            return self.banco.consultar(inteligentes, ordem=ordem)
        if lista == CAIXA:
            return self.banco.consultar(f"{_ATIVAS} AND projeto_id IS NULL", ordem=ordem)
        if isinstance(lista, str) and lista.startswith(PREFIXO_TAG):
            return self.banco.consultar(
                f"{ativas} AND id IN (SELECT tt.tarefa_id FROM tarefa_tag tt "
                "JOIN tag g ON g.id = tt.tag_id WHERE g.nome = ?)",
                (lista[len(PREFIXO_TAG):],), ordem)
        if isinstance(lista, str) and lista.startswith(PREFIXO_FILTRO):
            f = self.banco.obter_filtro(int(lista[len(PREFIXO_FILTRO):]))
            if f is None:
                return []
            return [t for t in self.banco.consultar(ativas, ordem=ordem)
                    if filtros_core.corresponde(t, f.criterios, hoje)]
        if isinstance(lista, int):  # id de projeto (também funciona para listas arquivadas)
            return self.banco.consultar(f"{_ATIVAS} AND projeto_id = ?", (lista,), ordem)
        raise ValueError(f"lista desconhecida: {lista!r}")

    def buscar(self, texto: str) -> list[Tarefa]:
        """Procura em título, notas e etiquetas, em todas as listas (menos lixeira)."""
        texto = texto.strip().lstrip("#")
        if not texto:
            return []
        like = f"%{texto}%"
        return self.banco.consultar(
            "apagada_em IS NULL AND (titulo LIKE ? OR notas LIKE ? OR id IN ("
            "SELECT tt.tarefa_id FROM tarefa_tag tt JOIN tag g ON g.id = tt.tag_id WHERE g.nome LIKE ?))",
            (like, like, like),
            "concluida_em IS NOT NULL, prazo IS NULL, prazo, prazo_hora IS NULL, prazo_hora, id",
        )

    def contagens(self, hoje: date | None = None) -> dict:
        res = {k: len(self.listar(k, hoje)) for k in (HOJE, AMANHA, PROXIMOS, TODAS, CAIXA, CONCLUIDAS, LIXEIRA)}
        for p in self.banco.listar_projetos() + self.banco.listar_projetos_arquivados():
            res[p.id] = len(self.listar(p.id, hoje))
        for g in self.banco.listar_tags():
            res[chave_tag(g.nome)] = len(self.listar(chave_tag(g.nome), hoje))
        for f in self.banco.listar_filtros():
            res[chave_filtro(f.id)] = len(self.listar(chave_filtro(f.id), hoje))
        return res
