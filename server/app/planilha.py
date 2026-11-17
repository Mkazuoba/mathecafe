"""Planilha .xlsx sem dependencia (so zipfile + XML), para os relatorios.

O formato e o Office Open XML minimo que o Excel, o LibreOffice e o Google
Planilhas abrem: textos inline, numeros, tempos como fracao do dia no formato
[h]:mm:ss (o Excel soma e passa de 24h), datas como numero de serie.

    gerar([Aba("Resumo", linhas, larguras=[30, 16])]) -> bytes

Cada linha e uma lista de valores: str, int, float, Duracao(segundos),
Porcentagem(0-100), datetime, date ou None. Negrito(valor) deixa a celula em
negrito; Aba(cabecalho=True) poe a primeira linha em negrito.
"""
import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, List, Optional
from xml.sax.saxutils import escape, quoteattr

EPOCA = datetime(1899, 12, 30)  # dia 0 do Excel (com o bug de 1900 ja compensado)

# indices em cellXfs (styles.xml)
NORMAL, NEGRITO, DURACAO, DATA_HORA, DATA, PORCENTO = range(6)


@dataclass
class Duracao:
    segundos: int


@dataclass
class Porcentagem:
    valor: Optional[float]  # 0 a 100; None fica em branco


@dataclass
class Negrito:
    valor: Any


@dataclass
class Aba:
    nome: str
    linhas: List[list]
    larguras: List[float] = field(default_factory=list)
    cabecalho: bool = True


def _coluna(i: int) -> str:
    letras = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        letras = chr(65 + r) + letras
    return letras


_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _celula(ref: str, valor, estilo: int = NORMAL) -> str:
    if isinstance(valor, Negrito):
        return _celula(ref, valor.valor, NEGRITO)
    if valor is None:
        return ""
    if isinstance(valor, bool):
        valor = "Sim" if valor else "Não"
    if isinstance(valor, Duracao):
        return f'<c r="{ref}" s="{DURACAO}"><v>{round(max(0, valor.segundos) / 86400, 10)!r}</v></c>'
    if isinstance(valor, Porcentagem):
        if valor.valor is None:
            return ""
        return f'<c r="{ref}" s="{PORCENTO}"><v>{round(valor.valor / 100, 6)!r}</v></c>'
    if isinstance(valor, datetime):
        serie = (valor - EPOCA).total_seconds() / 86400
        return f'<c r="{ref}" s="{DATA_HORA}"><v>{round(serie, 10)!r}</v></c>'
    if isinstance(valor, date):
        return f'<c r="{ref}" s="{DATA}"><v>{(valor - EPOCA.date()).days}</v></c>'
    if isinstance(valor, (int, float)):
        s = f' s="{estilo}"' if estilo else ""
        return f'<c r="{ref}"{s}><v>{valor!r}</v></c>'
    texto = escape(_CONTROLE.sub("", str(valor)))
    s = f' s="{estilo}"' if estilo else ""
    return f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{texto}</t></is></c>'


def _aba_xml(aba: Aba) -> str:
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>'
                   for i, w in enumerate(aba.larguras))
    linhas = []
    for n, linha in enumerate(aba.linhas, start=1):
        estilo = NEGRITO if (aba.cabecalho and n == 1) else NORMAL
        cels = "".join(_celula(f"{_coluna(i)}{n}", v, estilo) for i, v in enumerate(linha))
        linhas.append(f'<row r="{n}">{cels}</row>')
    congelar = ('<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
                'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>') if aba.cabecalho else ""
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'{congelar}{f"<cols>{cols}</cols>" if cols else ""}<sheetData>{"".join(linhas)}</sheetData></worksheet>')


_ESTILOS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<numFmts count="3"><numFmt numFmtId="164" formatCode="[h]:mm:ss"/>'
    '<numFmt numFmtId="165" formatCode="dd/mm/yyyy hh:mm"/><numFmt numFmtId="166" formatCode="0.0%"/></numFmts>'
    '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
    '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="6">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="166" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '</cellXfs></styleSheet>'
)


def _nome_aba(nome: str) -> str:
    return re.sub(r"[\[\]:*?/\\]", "", nome)[:31] or "Planilha"


def gerar(abas: List[Aba]) -> bytes:
    n = len(abas)
    tipos = "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                    for i in range(1, n + 1))
    folhas = "".join(f'<sheet name={quoteattr(_nome_aba(a.nome))} sheetId="{i}" r:id="rId{i}"/>'
                     for i, a in enumerate(abas, start=1))
    rels = "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                   f'relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, n + 1))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" '
                   'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" '
                   'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   f'{tipos}</Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                   'relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   f'<sheets>{folhas}</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   f'{rels}<Relationship Id="rId{n + 1}" Type="http://schemas.openxmlformats.org/officeDocument/'
                   '2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr("xl/styles.xml", _ESTILOS)
        for i, aba in enumerate(abas, start=1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", _aba_xml(aba))
    return buf.getvalue()
