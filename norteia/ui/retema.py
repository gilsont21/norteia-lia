"""Troca de tema ao vivo: reescreve os estilos e recolore os ícones dos widgets que já existem."""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import QAbstractButton, QLabel, QLineEdit, QWidget

from . import tema


def _distancia(a: str, b: str) -> int:
    return max(abs(int(a[k:k + 2], 16) - int(b[k:k + 2], 16)) for k in (1, 3, 5))


def _rgb(cor: str) -> tuple[int, int, int]:
    return int(cor[1:3], 16), int(cor[3:5], 16), int(cor[5:7], 16)


def _achar(cor: str, mapa: dict[str, str]) -> str | None:
    if cor in mapa:
        return mapa[cor]
    for antiga, nova in mapa.items():
        if len(antiga) == 7 and antiga.startswith("#") and _distancia(cor, antiga) <= 3:
            return nova
    return None


def _cores_do_desenho(img: QImage) -> list[str]:
    """As cores sólidas do desenho (uma por tom). Ícones de traço têm uma ou duas."""
    contagem: dict[str, int] = {}
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() >= 200:
                contagem[c.name().lower()] = contagem.get(c.name().lower(), 0) + 1
    grupos: list[str] = []
    for cor in sorted(contagem, key=contagem.get, reverse=True):    # as mais frequentes primeiro; o resto são misturas
        if all(_distancia(cor, g) > 24 for g in grupos):
            grupos.append(cor)
            if len(grupos) == 2:
                break
    return grupos


def recolorir(pm: QPixmap, mapa: dict[str, str]) -> QPixmap | None:
    """Recolore um ícone de uma ou duas cores (as bordas suaves entre elas continuam suaves)."""
    if pm.isNull():
        return None
    img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
    cores = _cores_do_desenho(img)
    if not cores:
        return None
    novas = [_achar(c, mapa) for c in cores]
    if all(n is None for n in novas):
        return None
    novas = [n or c for n, c in zip(novas, cores)]
    a = _rgb(cores[0])
    b = _rgb(cores[1]) if len(cores) == 2 else None
    na = _rgb(novas[0])
    nb = _rgb(novas[1]) if len(cores) == 2 else None
    saida = QImage(img.size(), QImage.Format_ARGB32)
    saida.setDevicePixelRatio(pm.devicePixelRatio())
    saida.fill(0)
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() == 0:
                continue
            if b is None:
                r, g, bl = na
            else:
                v = (c.red() - b[0], c.green() - b[1], c.blue() - b[2])
                d = (a[0] - b[0], a[1] - b[1], a[2] - b[2])
                t = sum(p * q for p, q in zip(v, d)) / max(1, sum(q * q for q in d))
                t = max(0.0, min(1.0, t))
                r, g, bl = (round(t * na[k] + (1 - t) * nb[k]) for k in range(3))
            saida.setPixelColor(x, y, QColor(r, g, bl, c.alpha()))
    return QPixmap.fromImage(saida)


def _icone(icone: QIcon, tamanho, mapa) -> QIcon | None:
    if icone.isNull():
        return None
    novo = recolorir(icone.pixmap(QSize(256, 256)), mapa)      # o desenho original, no maior tamanho guardado
    return None if novo is None else QIcon(novo)


def retemar(raiz: QWidget, mapa: dict[str, str]) -> None:
    """Aplica `mapa` (cor antiga -> cor nova) a `raiz` e a tudo o que há dentro dela."""
    if not mapa:
        return
    for w in [raiz, *raiz.findChildren(QWidget)]:
        estilo = w.styleSheet()
        if estilo:
            novo = tema.trocar_cores(estilo, mapa)
            if novo != estilo:
                w.setStyleSheet(novo)
        if isinstance(w, QAbstractButton) and w.objectName() != "btnAvatar":
            ic = _icone(w.icon(), w.iconSize(), mapa)
            if ic is not None:
                w.setIcon(ic)
        elif isinstance(w, QLabel):
            pm = w.pixmap()
            if pm is not None and not pm.isNull():
                novo_pm = recolorir(pm, mapa)
                if novo_pm is not None:
                    w.setPixmap(novo_pm)
        elif isinstance(w, QLineEdit):
            for a in w.actions():
                ic = _icone(a.icon(), QSize(16, 16), mapa)
                if ic is not None:
                    a.setIcon(ic)
        w.update()
