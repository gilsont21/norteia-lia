"""Provedores de IA do assistente: Gemini, Claude, ChatGPT (OpenAI) e DeepSeek.

Cada provedor tem um jeito próprio de receber mensagens e "ferramentas" (funções que a IA pode pedir para rodar).
Aqui tudo é convertido para um formato neutro, então o resto do app não sabe qual IA está do outro lado.

Histórico neutro (lista de dicionários):
  {"papel": "usuario",   "texto": "..."}
  {"papel": "assistente", "texto": "...", "chamadas": [{"id": "c1", "nome": "listar_tarefas", "args": {...}}]}
  {"papel": "ferramenta", "resultados": [{"id": "c1", "nome": "listar_tarefas", "conteudo": "..."}]}

A chave de API fica no cofre do sistema (Windows) e só é lida na hora de chamar a IA. A tela nunca a mostra.
"""
from __future__ import annotations

import json
import time as _tempo
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .google_agenda import Cofre
from .arquivos_ia import Anexo, texto_da_mensagem, texto_do_pdf
from .ia import ErroIA


class ErroHTTP(ErroIA):
    """Erro devolvido pelo provedor, com o código HTTP (para decidir se vale tentar de novo)."""

    def __init__(self, mensagem: str, codigo: int = 0):
        super().__init__(mensagem)
        self.codigo = codigo


TEMPORARIOS = (500, 502, 503, 504)      # sobrecarga ou falha passageira do provedor
PAUSAS_ENTRE_TENTATIVAS = (2.0, 5.0)    # segundos; 3 tentativas no total


@dataclass(frozen=True)
class Provedor:
    chave: str
    rotulo: str
    modelo_padrao: str
    formato: str            # "gemini", "claude" ou "openai" (também serve para o DeepSeek)
    base: str
    custo: str              # aviso mostrado na tela
    onde_chave: str         # onde a pessoa cria a chave
    le_imagem: bool = True
    le_pdf: bool = True
    voz: str = ""           # como transcreve áudio: "gemini", "openai" ou "" (não transcreve)


# Os nomes de modelo mudam com o tempo: cada um pode ser trocado no campo "Modelo" (avançado) da tela.
PROVEDORES: dict[str, Provedor] = {p.chave: p for p in (
    Provedor("gemini", "Gemini (Google)", "gemini-2.5-flash", "gemini",
             "https://generativelanguage.googleapis.com/v1beta",
             "Tem camada gratuita com limites. Na camada gratuita o Google pode usar o conteúdo enviado para "
             "melhorar os produtos dele.",
             "aistudio.google.com (Get API key)", voz="gemini"),
    Provedor("claude", "Claude (Anthropic)", "claude-sonnet-4-5", "claude", "https://api.anthropic.com/v1",
             "Cobrado por uso, à parte da assinatura do chat. Precisa de créditos na conta de API.",
             "console.anthropic.com (API keys)"),
    Provedor("openai", "ChatGPT (OpenAI)", "gpt-4o-mini", "openai", "https://api.openai.com/v1",
             "Cobrado por uso, à parte da assinatura do ChatGPT. Precisa de créditos na conta de API.",
             "platform.openai.com (API keys)", voz="openai"),
    Provedor("deepseek", "DeepSeek", "deepseek-chat", "openai", "https://api.deepseek.com",
             "Cobrado por uso (costuma ser barato). Confira os preços no site do provedor.",
             "platform.deepseek.com (API keys)", le_imagem=False, le_pdf=False),
)}
PROVEDOR_PADRAO = "gemini"


@dataclass
class Chamada:
    id: str
    nome: str
    args: dict


@dataclass
class Resposta:
    texto: str = ""
    chamadas: list[Chamada] = field(default_factory=list)
    bruto: list | None = None      # partes originais do Gemini (guardam a "assinatura de raciocínio" dos modelos novos)


# ---------------------------------------------------------------- chave no cofre
class CofreIA(Cofre):
    SERVICO = "app-tarefas-ia"
    PREFIXO_META = "ia_cofre_"


class ConfigIA:
    """Escolhas da pessoa: qual IA, qual modelo, e a chave (guardada no cofre, nunca devolvida à tela)."""

    def __init__(self, banco, cofre: Cofre | None = None):
        self.banco = banco
        self.cofre = cofre or CofreIA(banco)

    # ---- provedor ativo e modelo
    @property
    def ativo(self) -> str:
        v = self.banco.meta("ia_provedor", PROVEDOR_PADRAO) or PROVEDOR_PADRAO
        return v if v in PROVEDORES else PROVEDOR_PADRAO

    def definir_ativo(self, provedor: str) -> None:
        if provedor not in PROVEDORES:
            raise ValueError(f"provedor desconhecido: {provedor}")
        self.banco.definir_meta("ia_provedor", provedor)

    def modelo(self, provedor: str | None = None) -> str:
        p = provedor or self.ativo
        return (self.banco.meta(f"ia_modelo_{p}", "") or "").strip() or PROVEDORES[p].modelo_padrao

    def modelo_personalizado(self, provedor: str) -> str:
        return (self.banco.meta(f"ia_modelo_{provedor}", "") or "").strip()

    def definir_modelo(self, provedor: str, modelo: str) -> None:
        """Texto vazio volta ao modelo padrão."""
        self.banco.definir_meta(f"ia_modelo_{provedor}", modelo.strip())

    # ---- chave
    def tem_chave(self, provedor: str | None = None) -> bool:
        return bool(self.cofre.ler("chave_" + (provedor or self.ativo)))

    def salvar_chave(self, provedor: str, chave: str) -> None:
        chave = "".join(chave.split())          # tira espaços e quebras de linha de colagem
        if provedor not in PROVEDORES:
            raise ValueError(f"provedor desconhecido: {provedor}")
        if len(chave) < 8:
            raise ErroIA("Essa chave parece curta demais. Cole a chave inteira.")
        self.cofre.gravar("chave_" + provedor, chave)
        self.banco.definir_meta(f"ia_final_{provedor}", chave[-4:])

    def apagar_chave(self, provedor: str) -> None:
        self.cofre.apagar("chave_" + provedor)
        self.banco.definir_meta(f"ia_final_{provedor}", "")

    def mascara(self, provedor: str | None = None) -> str:
        """O único jeito de a tela "ver" a chave: os 4 últimos caracteres."""
        p = provedor or self.ativo
        if not self.tem_chave(p):
            return "sem chave"
        final = self.banco.meta(f"ia_final_{p}", "") or ""
        return f"chave salva, termina em …{final}" if final else "chave salva"

    def chave_para_uso(self, provedor: str | None = None) -> str:
        """Só para o código que chama a IA. Nunca mostrar, registrar em log nem exportar."""
        return self.cofre.ler("chave_" + (provedor or self.ativo))

    # ---- opções de privacidade e preferências
    @property
    def enviar_notas(self) -> bool:
        return (self.banco.meta("ia_enviar_notas", "1") or "1") == "1"

    def definir_enviar_notas(self, ligado: bool) -> None:
        self.banco.definir_meta("ia_enviar_notas", "1" if ligado else "0")

    @property
    def preferencias(self) -> list[str]:
        try:
            return [str(x) for x in json.loads(self.banco.meta("ia_preferencias", "[]") or "[]")]
        except ValueError:
            return []

    def definir_preferencias(self, linhas: list[str]) -> None:
        limpas = [l.strip()[:300] for l in linhas if l.strip()][:30]
        self.banco.definir_meta("ia_preferencias", json.dumps(limpas, ensure_ascii=False))

    def adicionar_preferencia(self, texto: str) -> None:
        atuais = self.preferencias
        if texto.strip() and texto.strip() not in atuais:
            self.definir_preferencias(atuais + [texto.strip()])

    def pedido(self) -> "Pedido":
        p = self.ativo
        return Pedido(p, self.modelo(p), self.chave_para_uso(p), self.enviar_notas, self.preferencias)


@dataclass
class Pedido:
    """Tudo o que a thread de rede precisa saber (a thread não toca no cofre nem na tela)."""
    provedor: str
    modelo: str
    chave: str
    enviar_notas: bool = True
    preferencias: list[str] = field(default_factory=list)

    def __repr__(self) -> str:          # nunca deixa a chave escapar em log ou mensagem de erro
        return f"Pedido({self.provedor}, {self.modelo}, chave=***)"


def preparar_anexos(provedor: str, anexos: list[Anexo]) -> list[dict]:
    """Anexos no formato guardado na mensagem, já adaptados ao que o provedor consegue ler."""
    prov = PROVEDORES[provedor]
    saida = []
    for a in anexos:
        if a.tipo == "imagem" and not prov.le_imagem:
            raise ErroIA(f"{prov.rotulo} não lê imagens. Troque para Gemini, Claude ou ChatGPT em Configurações de IA.")
        if a.tipo == "pdf" and not prov.le_pdf:
            a = Anexo(a.nome, "text/plain", texto=texto_do_pdf(a.dados)[:60_000])   # lê o texto do PDF aqui no PC
        saida.append(a.para_historico())
    return saida


def _texto_usuario(m: dict) -> str:
    t = texto_da_mensagem(m.get("texto", ""), m.get("anexos") or [])
    return t or "Veja o anexo."


def _midias(m: dict) -> list[dict]:
    return [a for a in (m.get("anexos") or []) if a.get("tipo") in ("imagem", "pdf", "audio") and a.get("b64")]


# ---------------------------------------------------------------- transporte
def transporte_http(url: str, cabecalhos: dict, corpo: bytes, timeout: float = 90.0) -> dict:
    req = urllib.request.Request(url, data=corpo, headers=cabecalhos, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalhe = ""
        try:
            bruto = json.loads(e.read().decode("utf-8"))
            erro = bruto.get("error", bruto) if isinstance(bruto, dict) else {}
            detalhe = erro.get("message", "") if isinstance(erro, dict) else str(erro)
        except (ValueError, OSError, AttributeError):
            pass
        raise ErroHTTP(_mensagem_http(e.code, detalhe), e.code) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErroIA(f"Não consegui falar com a IA (sem internet?): {e}") from e


def transporte_multipart(url: str, cabecalhos: dict, campos: dict, arquivo: tuple, timeout: float = 120.0) -> dict:
    """POST com arquivo (usado na transcrição de voz do ChatGPT). arquivo = (campo, nome, bytes, tipo)."""
    import uuid  # noqa: PLC0415
    limite = "----tarefas" + uuid.uuid4().hex
    partes = []
    for k, v in campos.items():
        partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    campo, nome, dados, tipo = arquivo
    partes.append((f'--{limite}\r\nContent-Disposition: form-data; name="{campo}"; filename="{nome}"\r\n'
                   f"Content-Type: {tipo}\r\n\r\n").encode() + dados + b"\r\n")
    partes.append(f"--{limite}--\r\n".encode())
    cab = {**cabecalhos, "content-type": f"multipart/form-data; boundary={limite}"}
    return transporte_http(url, cab, b"".join(partes), timeout)


def _mensagem_http(codigo: int, detalhe: str) -> str:
    detalhe = detalhe.strip()[:300]
    if codigo in (401, 403):
        return "A chave foi recusada. Confira a chave e o provedor escolhido em Configurações de IA."
    if codigo == 404:
        return "O modelo não foi encontrado. Troque o nome em Configurações de IA (Modelo, avançado)."
    if codigo == 429:
        return "Limite de uso da IA atingido. Espere um pouco ou use outra chave ou provedor."
    if codigo == 402:
        return "A conta da IA está sem saldo. Adicione créditos no site do provedor."
    if codigo in TEMPORARIOS:
        return (f"O provedor da IA está sobrecarregado ou instável agora (erro {codigo}). Isso costuma passar em "
                "alguns minutos. Tente de novo ou troque de IA ou de modelo em Configurações de IA.")
    return f"A IA respondeu com erro {codigo}. {detalhe}".strip()


# ---------------------------------------------------------------- conversão para cada provedor
def _esquema_gemini(esq: dict) -> dict:
    """O Gemini aceita só um subconjunto do esquema JSON."""
    ok = {"type", "description", "properties", "required", "items", "enum"}
    saida = {k: v for k, v in esq.items() if k in ok}
    if "properties" in saida:
        saida["properties"] = {k: _esquema_gemini(v) for k, v in saida["properties"].items()}
    if "items" in saida and isinstance(saida["items"], dict):
        saida["items"] = _esquema_gemini(saida["items"])
    return saida


def _pedido_gemini(prov: Provedor, modelo: str, chave: str, sistema: str, historico: list[dict],
                   ferramentas: list[dict]):
    conteudo = []
    for m in historico:
        if m["papel"] == "usuario":
            partes = [{"text": _texto_usuario(m)}] + [
                {"inlineData": {"mimeType": a["mime"], "data": a["b64"]}} for a in _midias(m)]
            conteudo.append({"role": "user", "parts": partes})
        elif m["papel"] == "assistente":
            partes = list(m.get("bruto_gemini") or [])
            if not partes:
                if m.get("texto"):
                    partes.append({"text": m["texto"]})
                for c in m.get("chamadas", []):
                    partes.append({"functionCall": {"name": c["nome"], "args": c["args"]}})
            conteudo.append({"role": "model", "parts": partes or [{"text": ""}]})
        else:
            conteudo.append({"role": "user", "parts": [
                {"functionResponse": {"name": r["nome"], "response": {"resultado": r["conteudo"]}}}
                for r in m["resultados"]]})
    corpo = {"systemInstruction": {"parts": [{"text": sistema}]}, "contents": conteudo}
    if ferramentas:
        corpo["tools"] = [{"functionDeclarations": [
            {"name": f["nome"], "description": f["descricao"], "parameters": _esquema_gemini(f["parametros"])}
            for f in ferramentas]}]
    url = f"{prov.base}/models/{modelo}:generateContent"
    return url, {"content-type": "application/json", "x-goog-api-key": chave}, corpo


def _resposta_gemini(dados: dict) -> Resposta:
    cands = dados.get("candidates") or []
    if not cands:
        motivo = (dados.get("promptFeedback") or {}).get("blockReason", "")
        raise ErroIA("A IA não devolveu resposta" + (f" ({motivo})." if motivo else "."))
    r = Resposta()
    partes = (cands[0].get("content") or {}).get("parts", [])
    r.bruto = partes if any("functionCall" in p for p in partes) else None
    for i, p in enumerate(partes):
        if "text" in p:
            r.texto += p["text"]
        elif "functionCall" in p:
            fc = p["functionCall"]
            r.chamadas.append(Chamada(f"g{i}", fc["name"], dict(fc.get("args") or {})))
    return r


def _pedido_claude(prov: Provedor, modelo: str, chave: str, sistema: str, historico: list[dict],
                   ferramentas: list[dict]):
    msgs = []
    for m in historico:
        if m["papel"] == "usuario":
            midias = _midias(m)
            if not midias:
                msgs.append({"role": "user", "content": _texto_usuario(m)})
            else:
                blocos = [{"type": "image" if a["tipo"] == "imagem" else "document",
                           "source": {"type": "base64", "media_type": a["mime"], "data": a["b64"]}} for a in midias]
                msgs.append({"role": "user", "content": blocos + [{"type": "text", "text": _texto_usuario(m)}]})
        elif m["papel"] == "assistente":
            blocos = []
            if m.get("texto"):
                blocos.append({"type": "text", "text": m["texto"]})
            for c in m.get("chamadas", []):
                blocos.append({"type": "tool_use", "id": c["id"], "name": c["nome"], "input": c["args"]})
            msgs.append({"role": "assistant", "content": blocos or [{"type": "text", "text": "..."}]})
        else:
            msgs.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": r["id"], "content": r["conteudo"]} for r in m["resultados"]]})
    corpo = {"model": modelo, "max_tokens": 2048, "system": sistema, "messages": msgs}
    if ferramentas:
        corpo["tools"] = [{"name": f["nome"], "description": f["descricao"], "input_schema": f["parametros"]}
                          for f in ferramentas]
    return (f"{prov.base}/messages",
            {"content-type": "application/json", "x-api-key": chave, "anthropic-version": "2023-06-01"}, corpo)


def _resposta_claude(dados: dict) -> Resposta:
    r = Resposta()
    for b in dados.get("content", []):
        if b.get("type") == "text":
            r.texto += b.get("text", "")
        elif b.get("type") == "tool_use":
            r.chamadas.append(Chamada(b["id"], b["name"], dict(b.get("input") or {})))
    return r


def _pedido_openai(prov: Provedor, modelo: str, chave: str, sistema: str, historico: list[dict],
                   ferramentas: list[dict]):
    msgs = [{"role": "system", "content": sistema}]
    for m in historico:
        if m["papel"] == "usuario":
            midias = _midias(m)
            if not midias:
                msgs.append({"role": "user", "content": _texto_usuario(m)})
            else:
                partes = [{"type": "text", "text": _texto_usuario(m)}]
                for a in midias:
                    url = f"data:{a['mime']};base64,{a['b64']}"
                    partes.append({"type": "image_url", "image_url": {"url": url}} if a["tipo"] == "imagem" else
                                  {"type": "file", "file": {"filename": a["nome"], "file_data": url}})
                msgs.append({"role": "user", "content": partes})
        elif m["papel"] == "assistente":
            x = {"role": "assistant", "content": m.get("texto") or None}
            if m.get("chamadas"):
                x["tool_calls"] = [{"id": c["id"], "type": "function",
                                    "function": {"name": c["nome"], "arguments": json.dumps(c["args"], ensure_ascii=False)}}
                                   for c in m["chamadas"]]
            msgs.append(x)
        else:
            for r in m["resultados"]:
                msgs.append({"role": "tool", "tool_call_id": r["id"], "content": r["conteudo"]})
    corpo = {"model": modelo, "messages": msgs}
    if ferramentas:
        corpo["tools"] = [{"type": "function", "function": {"name": f["nome"], "description": f["descricao"],
                                                            "parameters": f["parametros"]}} for f in ferramentas]
    return (f"{prov.base}/chat/completions",
            {"content-type": "application/json", "authorization": f"Bearer {chave}"}, corpo)


def _resposta_openai(dados: dict) -> Resposta:
    escolhas = dados.get("choices") or []
    if not escolhas:
        raise ErroIA("A IA não devolveu resposta.")
    msg = escolhas[0].get("message") or {}
    r = Resposta(texto=msg.get("content") or "")
    for c in msg.get("tool_calls") or []:
        fn = c.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = {}
        r.chamadas.append(Chamada(c.get("id") or fn.get("name", "c"), fn.get("name", ""), args if isinstance(args, dict) else {}))
    return r


_FORMATOS = {"gemini": (_pedido_gemini, _resposta_gemini), "claude": (_pedido_claude, _resposta_claude),
             "openai": (_pedido_openai, _resposta_openai)}


def conversar(pedido: Pedido, sistema: str, historico: list[dict], ferramentas: list[dict] | None = None,
              transporte=transporte_http, pausar=_tempo.sleep) -> Resposta:
    """Uma ida à IA. Devolve o texto e/ou as ferramentas que ela quer rodar."""
    if pedido.provedor not in PROVEDORES:
        raise ErroIA("Escolha uma IA nas configurações.")
    if not pedido.chave:
        raise ErroIA(f"Falta a chave de {PROVEDORES[pedido.provedor].rotulo}. Cole a chave em Configurações de IA.")
    prov = PROVEDORES[pedido.provedor]
    montar, ler = _FORMATOS[prov.formato]
    url, cabecalhos, corpo = montar(prov, pedido.modelo, pedido.chave, sistema, historico, ferramentas or [])
    corpo_json = json.dumps(corpo).encode("utf-8")
    for tentativa in range(len(PAUSAS_ENTRE_TENTATIVAS) + 1):
        try:
            dados = transporte(url, cabecalhos, corpo_json)
            break
        except ErroHTTP as e:
            if e.codigo not in TEMPORARIOS or tentativa >= len(PAUSAS_ENTRE_TENTATIVAS):
                raise
            pausar(PAUSAS_ENTRE_TENTATIVAS[tentativa])      # sobrecarga passageira: espera e tenta de novo
    return ler(dados)


def testar_conexao(pedido: Pedido, transporte=transporte_http) -> str:
    r = conversar(pedido, "Responda sempre em português do Brasil, bem curto.",
                  [{"papel": "usuario", "texto": "Responda apenas: ok"}], None, transporte)
    return r.texto.strip() or "(sem texto)"


def quebrar_tarefa(pedido: Pedido, titulo: str, notas: str = "", transporte=transporte_http, maximo: int = 8) -> list[str]:
    """Subtarefas sugeridas pela IA escolhida (sem ferramentas). Só o título e as notas vão para a IA."""
    from .ia import _extrair_lista  # noqa: PLC0415
    if not titulo.strip():
        raise ErroIA("A tarefa precisa de um título.")
    texto = (f"Quebre a tarefa abaixo em no máximo {maximo} subtarefas curtas, concretas e em ordem de execução. "
             "Responda SOMENTE com uma lista JSON de textos em português do Brasil, sem comentários.\n\n"
             f"Tarefa: {titulo.strip()}\n" + (f"Detalhes: {notas.strip()[:2000]}\n" if notas.strip() else ""))
    r = conversar(pedido, "Você ajuda a organizar tarefas.", [{"papel": "usuario", "texto": texto}], None, transporte)
    lista = _extrair_lista(r.texto)[:maximo]
    if not lista:
        raise ErroIA("A resposta veio vazia.")
    return lista


PROMPT_TRANSCRICAO = ("Transcreva fielmente o áudio em português do Brasil. Responda SOMENTE com a transcrição, sem "
                      "comentários, sem aspas e sem rótulos. Se não houver fala, responda com texto vazio.")


def transcrever(pedido: Pedido, wav: bytes, transporte=transporte_http, transporte_arquivo=transporte_multipart,
                pausar=_tempo.sleep) -> str:
    """Voz para texto usando a IA escolhida. Só Gemini e ChatGPT aceitam áudio."""
    import base64  # noqa: PLC0415
    prov = PROVEDORES.get(pedido.provedor)
    if prov is None:
        raise ErroIA("Escolha uma IA nas configurações.")
    if not prov.voz:
        raise ErroIA(f"{prov.rotulo} não transcreve voz. Troque para Gemini ou ChatGPT em Configurações de IA, "
                     "ou use o ditado do Windows (tecla Windows + H) na caixa de texto.")
    if not pedido.chave:
        raise ErroIA(f"Falta a chave de {prov.rotulo}. Cole a chave em Configurações de IA.")
    if prov.voz == "gemini":
        audio = {"nome": "voz.wav", "mime": "audio/wav", "tipo": "audio", "b64": base64.b64encode(wav).decode("ascii")}
        r = conversar(pedido, "Você transcreve áudio.", [{"papel": "usuario", "texto": PROMPT_TRANSCRICAO,
                                                          "anexos": [audio]}], None, transporte, pausar)
        return r.texto.strip()
    url = f"{prov.base}/audio/transcriptions"
    cab = {"authorization": f"Bearer {pedido.chave}"}
    for tentativa in range(len(PAUSAS_ENTRE_TENTATIVAS) + 1):
        try:
            dados = transporte_arquivo(url, cab, {"model": "whisper-1", "language": "pt"},
                                       ("file", "voz.wav", wav, "audio/wav"))
            break
        except ErroHTTP as e:
            if e.codigo not in TEMPORARIOS or tentativa >= len(PAUSAS_ENTRE_TENTATIVAS):
                raise
            pausar(PAUSAS_ENTRE_TENTATIVAS[tentativa])
    return str(dados.get("text", "")).strip()
