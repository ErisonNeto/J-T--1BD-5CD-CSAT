"""Exportação privada de investigação operacional — identificadores preservados como texto."""
from __future__ import annotations

from io import BytesIO
from typing import Iterable

from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

EXCEL_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def gerar_excel(titulo: str, campos: list[tuple[str, str]], registros: Iterable[dict],
                arquivo: str, observacao: str = '') -> StreamingResponse:
    """Uma linha por registro; números de remessa/ticket/ID ficam como TEXTO.

    campos contém pares (cabeçalho, chave do dicionário).
    Não executa fórmulas originadas de strings da base.
    """
    wb = Workbook(write_only=True)
    ws = wb.create_sheet('Remessas')
    ws.freeze_panes = 'A2'
    cabecalhos = []
    for nome, _ in campos:
        cell = WriteOnlyCell(ws, value=nome)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill(fill_type='solid', fgColor='B51C2A')
        cabecalhos.append(cell)
    ws.append(cabecalhos)
    total = 0
    for registro in registros:
        linha = []
        for _, chave in campos:
            valor = registro.get(chave)
            if valor is None:
                linha.append('')
            elif isinstance(valor, bool):
                linha.append('Sim' if valor else 'Não')
            elif isinstance(valor, (int, float)) and chave not in ('remessa', 'tracking', 'ticket',
                                                                    'package_id', 'id', 'codigo'):
                linha.append(valor)
            else:
                cell = WriteOnlyCell(ws, value=str(valor))
                # Excel não pode interpretar identificadores como números nem fórmulas.
                cell.data_type = 's'
                cell.number_format = '@'
                linha.append(cell)
        ws.append(linha)
        total += 1
    if total:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(campos))}{total + 1}"
    for i, (nome, _) in enumerate(campos, 1):
        ws.column_dimensions[get_column_letter(i)].width = min(38, max(17, len(nome) + 4))

    instr = wb.create_sheet('Informações')
    instr.append(['Indicador', titulo])
    instr.append(['Registros exportados', total])
    instr.append(['Importante', 'Cada linha representa um registro/avaliação ou snapshot, conforme o indicador.'])
    instr.append(['Identificadores', 'Remessa, ticket, tracking e Package ID são texto; não arredondar nem converter para número.'])
    if observacao:
        instr.append(['Critério', observacao])

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(iter(lambda: buffer.read(65536), b''),
        media_type=EXCEL_MIME,
        headers={
            'Content-Disposition': f'attachment; filename="{arquivo}"',
            'Cache-Control': 'private, no-store',
            'X-Content-Type-Options': 'nosniff',
        })
