"""Arquivos que a pessoa anexa na conversa com a IA (imagens, PDF, texto, Word) e o áudio da voz.

Texto vira texto na mensagem (funciona em qualquer IA). Imagem e PDF seguem no formato próprio de cada provedor, e só
nos provedores que sabem lê-los. Os dados ficam na memória durante a conversa; o que vai para o banco local guarda só
o nome do arquivo.
"""
from __future__ import annotations

import base64
import io
import mimetypes
import re
import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .ia import ErroIA

MAX_ANEXOS = 5
LIMITE_IMAGEM = 6 * 1024 * 1024
LIMITE_PDF = 12 * 1024 * 1024
LIMITE_TEXTO_BYTES = 2 * 1024 * 1024
LIMITE_TEXTO_CARACTERES = 60_000

IMAGENS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
           ".gif": "image/gif"}
EXT_TEXTO = {".txt", ".md", ".csv", ".tsv", ".json", ".ics", ".xml", ".html", ".htm", ".log", ".py", ".js", ".ts",
             ".java", ".c", ".cpp", ".h", ".sql", ".yaml", ".yml", ".ini", ".cfg", ".rtf", ".tex", ".bib"}


@dataclass
class Anexo:
    nome: str
    mime: str
    dados: bytes = b""          # imagem ou PDF (bytes originais)
    texto: str = ""             # arquivos de texto, Word e PDF lido localmente

    @property
    def tipo(self) -> str:
        if self.mime.startswith("image/"):
            return "imagem"
        if self.mime == "application/pdf" and self.dados:
            return "pdf"
        return "texto"

    def b64(self) -> str:
        return base64.b64encode(self.dados).decode("ascii")

    def para_historico(self) -> dict:
        """Forma guardada na mensagem (JSON). `b64` só existe enquanto a conversa está aberta."""
        d = {"nome": self.nome, "mime": self.mime, "tipo": self.tipo}
        if self.tipo == "texto":
            d["texto"] = self.texto
        else:
            d["b64"] = self.b64()
        return d


def _cortar(texto: str) -> str:
    if len(texto) <= LIMITE_TEXTO_CARACTERES:
        return texto
    return texto[:LIMITE_TEXTO_CARACTERES] + "\n[... texto cortado por ser muito longo ...]"


def _texto_docx(dados: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(dados)) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except (zipfile.BadZipFile, KeyError) as e:
        raise ErroIA("Não consegui abrir esse arquivo do Word.") from e
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    texto = re.sub(r"<[^>]+>", "", xml)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
        texto = texto.replace(a, b)
    return texto.strip()


def texto_do_pdf(dados: bytes) -> str:
    """Leitura local do PDF (para IAs que não aceitam PDF). Precisa do pacote opcional `pypdf`."""
    try:
        from pypdf import PdfReader  # noqa: PLC0415
    except ImportError as e:
        raise ErroIA("Essa IA não lê PDF direto, e o leitor local de PDF (pypdf) não está instalado. "
                     "Use Gemini, Claude ou ChatGPT para PDFs.") from e
    try:
        leitor = PdfReader(io.BytesIO(dados))
        texto = "\n".join((p.extract_text() or "") for p in leitor.pages)
    except Exception as e:  # noqa: BLE001
        raise ErroIA("Não consegui ler esse PDF.") from e
    if not texto.strip():
        raise ErroIA("Esse PDF não tem texto selecionável (talvez seja escaneado). Tente anexar como imagem.")
    return texto


def carregar_bytes(nome: str, dados: bytes) -> Anexo:
    ext = Path(nome).suffix.lower()
    if ext in IMAGENS:
        if len(dados) > LIMITE_IMAGEM:
            raise ErroIA(f"A imagem “{nome}” é grande demais (limite de {LIMITE_IMAGEM // 1024 // 1024} MB).")
        return Anexo(nome, IMAGENS[ext], dados=dados)
    if ext == ".pdf":
        if len(dados) > LIMITE_PDF:
            raise ErroIA(f"O PDF “{nome}” é grande demais (limite de {LIMITE_PDF // 1024 // 1024} MB).")
        return Anexo(nome, "application/pdf", dados=dados)
    if ext == ".docx":
        return Anexo(nome, "text/plain", texto=_cortar(_texto_docx(dados)))
    if ext in EXT_TEXTO or (mimetypes.guess_type(nome)[0] or "").startswith("text/"):
        if len(dados) > LIMITE_TEXTO_BYTES:
            raise ErroIA(f"O arquivo “{nome}” é grande demais para ler como texto.")
        for cod in ("utf-8-sig", "cp1252"):
            try:
                return Anexo(nome, "text/plain", texto=_cortar(dados.decode(cod)))
            except UnicodeDecodeError:
                continue
    raise ErroIA(f"Ainda não sei ler arquivos do tipo “{ext or 'desconhecido'}”. Use imagem, PDF, Word (.docx) "
                 "ou texto.")


def carregar_arquivo(caminho: str | Path) -> Anexo:
    p = Path(caminho)
    try:
        return carregar_bytes(p.name, p.read_bytes())
    except OSError as e:
        raise ErroIA(f"Não consegui abrir “{p.name}”.") from e


def texto_da_mensagem(texto: str, anexos: list[dict]) -> str:
    """Junta o que a pessoa escreveu com o conteúdo dos arquivos de texto (que vão como texto puro)."""
    partes = [texto.strip()] if texto.strip() else []
    for a in anexos:
        if a.get("tipo") == "texto":
            partes.append(f"[Arquivo anexado: {a['nome']}]\n{a.get('texto', '')}")
    return "\n\n".join(partes)


def descricao_para_guardar(anexos: list[dict]) -> list[dict]:
    """Versão sem os dados (para o banco): só nome e tipo."""
    return [{"nome": a["nome"], "mime": a.get("mime", ""), "tipo": a.get("tipo", "texto"),
             **({"texto": a.get("texto", "")} if a.get("tipo") == "texto" else {})} for a in anexos]


# ---------------------------------------------------------------- áudio
def wav_de_pcm16(pcm: bytes, taxa: int = 16000, canais: int = 1) -> bytes:
    """Empacota amostras PCM de 16 bits em um arquivo .wav."""
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, canais, taxa, taxa * canais * 2, canais * 2, 16) +
            b"data" + struct.pack("<I", len(pcm)) + pcm)


def nivel_do_pcm16(pcm: bytes) -> float:
    """Volume de um trecho de áudio entre 0 e 1 (raiz da média dos quadrados)."""
    n = len(pcm) // 2
    if n == 0:
        return 0.0
    amostras = struct.unpack("<" + "h" * n, pcm[: n * 2])
    soma = sum(a * a for a in amostras)
    return min(1.0, (soma / n) ** 0.5 / 12000.0)


class ConversorPCM:
    """Converte o áudio que o microfone entrega (qualquer taxa, canais e formato) para PCM 16 bits, 16 kHz, mono.

    Guarda a posição entre os blocos, então dá para ir alimentando aos poucos enquanto a pessoa fala.
    """
    TAMANHOS = {"int16": 2, "int32": 4, "float": 4, "uint8": 1}

    def __init__(self, taxa: int = 16000, canais: int = 1, formato: str = "int16", destino: int = 16000):
        if formato not in self.TAMANHOS:
            raise ValueError(f"formato de áudio desconhecido: {formato}")
        self.taxa, self.canais, self.formato, self.destino = max(1, taxa), max(1, canais), formato, destino
        self._pos = 0.0                  # posição fracionária (em quadros de entrada) do próximo quadro de saída
        self._resto = b""                # bytes que não completaram um quadro

    @property
    def sem_conversao(self) -> bool:
        return self.taxa == self.destino and self.canais == 1 and self.formato == "int16"

    def _mono(self, dados: bytes) -> list[float]:
        import array  # noqa: PLC0415
        codigo = {"int16": "h", "int32": "i", "float": "f", "uint8": "B"}[self.formato]
        v = array.array(codigo)
        v.frombytes(dados)
        escala = {"int16": 1.0, "int32": 1 / 65536.0, "float": 32767.0, "uint8": 256.0}[self.formato]
        desloc = -128.0 if self.formato == "uint8" else 0.0
        c = self.canais
        quadros = len(v) // c
        if c == 1:
            return [(x + desloc) * escala for x in v]
        return [(sum(v[i * c:(i + 1) * c]) / c + desloc) * escala for i in range(quadros)]

    def converter(self, dados: bytes) -> bytes:
        if self.sem_conversao:
            return dados
        dados = self._resto + dados
        tam = self.TAMANHOS[self.formato] * self.canais
        usar = len(dados) - len(dados) % tam
        self._resto = dados[usar:]
        if usar == 0:
            return b""
        amostras = self._mono(dados[:usar])
        passo = self.taxa / self.destino
        saida = []
        pos = self._pos
        n = len(amostras)
        while pos < n:
            saida.append(max(-32768, min(32767, int(amostras[int(pos)]))))
            pos += passo
        self._pos = pos - n
        return struct.pack("<" + "h" * len(saida), *saida)
