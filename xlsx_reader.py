"""Leitor XLSX incremental usando apenas a biblioteca padrão.
Preserva as avaliações individuais; não depende de pandas/openpyxl.
"""
from __future__ import annotations

import datetime as dt
import posixpath
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def normalizar(texto: object) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c)).upper()
    return re.sub(r"[^A-Z0-9]", "", texto)


def data_excel(valor: object) -> str:
    if valor in (None, ""):
        raise ValueError("Data de avaliação vazia")
    s = str(valor).strip()
    try:
        return (dt.datetime(1899, 12, 30) + dt.timedelta(days=float(s))).date().isoformat()
    except (ValueError, OverflowError):
        pass
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(s[:10], fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Data de avaliação não reconhecida: {s}")


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    result = []
    with z.open("xl/sharedStrings.xml") as stream:
        for event, elem in ET.iterparse(stream, events=("end",)):
            if elem.tag == MAIN + "si":
                result.append("".join((child.text or "") for child in elem.iter(MAIN + "t")))
                elem.clear()
    return result


def _find_sheet(z: zipfile.ZipFile, title: str) -> str:
    workbook = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    mappings = {r.get("Id"): r.get("Target") for r in rels.findall(PKG_REL + "Relationship")}
    for sheet in workbook.findall(".//" + MAIN + "sheet"):
        if sheet.get("name", "").strip().casefold() == title.strip().casefold():
            target = mappings[sheet.attrib[REL + "id"]]
            p = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            if p not in z.namelist():
                raise ValueError(f"Arquivo não encontrou a aba {title}: {p}")
            return p
    raise ValueError(f"Aba obrigatória não encontrada: {title}")


def ler_aba(arquivo: str | Path, titulo: str):
    with zipfile.ZipFile(arquivo) as z:
        strings = _shared_strings(z)
        sheet_path = _find_sheet(z, titulo)
        with z.open(sheet_path) as stream:
            for event, elem in ET.iterparse(stream, events=("end",)):
                if elem.tag != MAIN + "row":
                    continue
                row = {}
                for cell in elem.findall(MAIN + "c"):
                    col = re.sub(r"\d", "", cell.get("r", ""))
                    raw = cell.find(MAIN + "v")
                    val = "" if raw is None else (raw.text or "")
                    if cell.get("t") == "s" and val:
                        val = strings[int(val)]
                    elif cell.get("t") == "inlineStr":
                        val = "".join((part.text or "") for part in cell.iter(MAIN + "t"))
                    row[col] = val
                yield row
                elem.clear()
