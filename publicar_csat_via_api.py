"""J&T Qualidade | CSAT TikTok, XLSX -> PostgreSQL jt_indicadores via JT API.

Coluna D: semana oficial. Coluna O: BASE cruzada pela Gestão (R/M Orlean).
Coluna S: avaliação binária (1=positiva, 0=negativa).
Não modifica tabelas do 1BD nem do 5CD; dados da Gestão são uma foto do arquivo.

Auditoria (sem gravação):  python publicar_csat_via_api.py
Publicação: python publicar_csat_via_api.py --aplicar --confirmar-banco jt_indicadores
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
import os
from pathlib import Path
import re
import sys
import time

import requests
from dotenv import load_dotenv
from xlsx_reader import ler_aba, normalizar, data_excel

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env', override=False)
URL = os.getenv('JT_API_URL', '').strip().rstrip('/')
KEY = os.getenv('JT_API_KEY', '').strip()
ORLEAN = normalizar('ORLEAN DA SILVA DO NASCIMENTO')
TABELA = 'jt_csat_registros'
CAMPOS = (
    'id', 'ano', 'semana_numero', 'semana_id', 'semana_descricao',
    'data_avaliacao', 'base_chave', 'base', 'codigo', 'uf', 'rm',
    'coordenador', 'supervisor', 'sc', 'tipo_sc', 'avaliacao',
    'ticket', 'tracking', 'categoria', 'arquivo_origem',
)


def localizar_arquivo(pasta: Path, termo: str) -> Path:
    resultados = [p for p in pasta.glob('*.xlsx') if termo in p.name.lower()
                  and not p.name.startswith('~$')]
    if not resultados:
        raise RuntimeError(f'Não encontrei XLSX de {termo} na pasta dados/.')
    return max(resultados, key=lambda p: p.stat().st_mtime)


def gestao_atual(path: Path):
    grupos = defaultdict(list)
    for n, r in enumerate(ler_aba(path, 'Responsáveis atuais')):
        if n == 0:
            for col, esperado in {'A': 'NOME DA BASE', 'G': 'RESPONSAVEL DA REGIAO',
                                  'H': 'COORDENADOR', 'I': 'SUPERVISOR'}.items():
                if normalizar(esperado) not in normalizar(r.get(col, '')):
                    raise RuntimeError(f'Gestão: cabeçalho {col} inesperado.')
            continue
        nome = r.get('A', '').strip()
        if not nome:
            continue
        codigo, uf = r.get('B', '').strip(), r.get('F', '').strip().upper()
        rm, coord, sup = (r.get(c, '').strip() for c in ('G', 'H', 'I'))
        sc = coord or sup
        tipo = 'Coordenador' if coord else ('Supervisor' if sup else 'Sem S/C')
        grupos[normalizar(nome)].append((codigo, nome, uf, rm, coord, sup, sc, tipo))
    validos, conflitos = {}, {}
    for chave, vals in grupos.items():
        atribuicoes = {(v[0], normalizar(v[3]), normalizar(v[4]), normalizar(v[5])) for v in vals}
        if len(atribuicoes) == 1:
            validos[chave] = vals[0]
        else:
            conflitos[chave] = vals
    return validos, conflitos


def parse_ano(r: dict, semana: int) -> int:
    # Ano deriva da data de avaliação; a semana é SEMPRE a da coluna D.
    h = r.get('H', '').strip()
    if h:
        try:
            return int(data_excel(h)[:4])
        except (ValueError, OverflowError):
            pass
    # A fonte auditada é W44/W45 de 2026; se o cabeçalho mudar e H ficar vazio,
    # o registro é ignorado em vez de se atribuir automaticamente ao ano errado.
    raise ValueError('Não foi possível determinar o ano pelo campo H.')


def ler_avaliacoes(arquivo: Path, gestao: dict):
    rows = []
    stats = Counter()
    faltantes = Counter()
    por_semana = defaultdict(lambda: Counter())
    rep = Counter()
    vistos = False
    vazio_seguido = 0
    for num_linha, r in enumerate(ler_aba(arquivo, 'BASE')):
        stats['linhas_lidas'] += 1
        if num_linha == 0:
            checks = {'D': 'WEEK', 'O': 'BASE', 'S': 'AVALIACAO'}
            for col, esperado in checks.items():
                if normalizar(r.get(col, '')) != esperado:
                    raise RuntimeError(f'Aba BASE: coluna {col} não corresponde a {esperado}.')
            continue
        semana_raw = r.get('D', '').strip()
        base_original = r.get('O', '').strip()
        nota_raw = r.get('S', '').strip()
        if not semana_raw and not base_original and not nota_raw:
            vazio_seguido += 1
            if vistos and vazio_seguido >= 5000:
                print('  Leitura encerrada após 5.000 linhas seguidas vazias/formatadas.')
                break
            continue
        vistos, vazio_seguido = True, 0
        stats['linhas_operacionais'] += 1
        m = re.match(r'^W\s*(\d{1,2})(?:\b|\s)', semana_raw, re.IGNORECASE)
        if not m:
            stats['semana_invalida'] += 1
            continue
        semana = int(m.group(1))
        if not 1 <= semana <= 53:
            stats['semana_invalida'] += 1
            continue
        if nota_raw not in ('0', '1'):
            stats['avaliacao_invalida'] += 1
            continue
        base_key = normalizar(base_original)
        gest = gestao.get(base_key)
        if not gest:
            stats['sem_gestao'] += 1
            faltantes[base_original] += 1
            continue
        if normalizar(gest[3]) != ORLEAN:
            stats['outra_rm'] += 1
            continue
        try:
            ano = parse_ano(r, semana)
            data_avaliacao = data_excel(r.get('H', ''))
        except ValueError:
            stats['data_invalida'] += 1
            continue
        id_semana = f'{ano}-W{semana:02d}'
        ticket, tracking = r.get('G', '').strip(), r.get('L', '').strip()
        # A chave não contém a avaliação: uma eventual retificação 0->1 vira UPSERT.
        identidade = (id_semana, ticket, base_key, tracking, data_avaliacao)
        rep[identidade] += 1
        uid = hashlib.sha256(('csat|' + '|'.join(identidade) + f'|{rep[identidade]}').encode('utf-8')).hexdigest()
        codigo, nome, uf, rm, coord, sup, sc, tipo = gest
        row = dict(zip(CAMPOS, (
            uid, ano, semana, id_semana, semana_raw, data_avaliacao,
            base_key, nome, codigo, uf, rm, coord, sup, sc, tipo,
            int(nota_raw), ticket, tracking, r.get('F', '').strip(), arquivo.name,
        )))
        rows.append(row)
        stats['orlean'] += 1
        por_semana[id_semana]['total'] += 1
        por_semana[id_semana]['sim'] += int(nota_raw)
    if not rows:
        raise RuntimeError('Nenhuma avaliação do R/M Orlean válida na aba BASE.')
    return rows, stats, faltantes, por_semana


def post(sess, endpoint, json, retries=3):
    for tentativa in range(retries):
        try:
            resp = sess.post(f'{URL}{endpoint}', headers={'X-API-Key': KEY}, json=json, timeout=120)
        except requests.RequestException as exc:
            if tentativa == retries-1:
                raise RuntimeError(f'JT API inacessível: {type(exc).__name__}') from exc
            time.sleep(2 + tentativa * 2)
            continue
        if resp.ok:
            try:
                return resp.json()
            except ValueError:
                raise RuntimeError(f'JT API {endpoint} não retornou JSON.')
        if resp.status_code in (429, 500, 502, 503, 504) and tentativa < retries-1:
            time.sleep(2 + tentativa * 2)
            continue
        raise RuntimeError(f'JT API {endpoint} HTTP {resp.status_code}; conteúdo omitido por segurança.')
    raise RuntimeError('JT API falhou após múltiplas tentativas.')


def query(sess, sql, params=None):
    data = post(sess, '/query', {'sql': sql, 'params': params or []})
    if isinstance(data, dict):
        for k in ('rows', 'data', 'result', 'resultado', 'registros'):
            if isinstance(data.get(k), list):
                return data[k]
    if isinstance(data, list):
        return data
    raise RuntimeError('JT API retornou formato de consulta inesperado.')


def scalar(sess, sql, params=None):
    rows = query(sess, sql, params)
    if not rows:
        return None
    first = rows[0]
    return next(iter(first.values())) if isinstance(first, dict) else first[0]


def main():
    parser = argparse.ArgumentParser(description='CSAT TikTok -> JT API PostgreSQL, somente Orlean')
    parser.add_argument('--arquivo', type=Path)
    parser.add_argument('--gestao', type=Path)
    parser.add_argument('--aplicar', action='store_true')
    parser.add_argument('--confirmar-banco', default='')
    parser.add_argument('--lote', type=int, default=200)
    args = parser.parse_args()
    if not 10 <= args.lote <= 500:
        parser.error('--lote deve ficar entre 10 e 500.')
    dados = ROOT / 'dados'
    arquivo = args.arquivo or localizar_arquivo(dados, 'csat')
    gestao_path = args.gestao or localizar_arquivo(dados, 'gestão de colaboradores')
    if not arquivo.is_file() or not gestao_path.is_file():
        parser.error('A planilha CSAT e a Gestão devem existir em dados/.')
    validos, conflitos = gestao_atual(gestao_path)
    rows, stats, faltantes, semanas = ler_avaliacoes(arquivo, validos)
    print('CSAT:', arquivo.name)
    print('Gestão:', gestao_path.name, '| bases válidas:', len(validos), '| conflitos:', len(conflitos))
    print('  Bases Orlean:', sum(normalizar(g[3]) == ORLEAN for g in validos.values()))
    print('Leitura:', stats['linhas_lidas'], 'linhas examinadas |', stats['linhas_operacionais'], 'operacionais')
    print('  Outra RM:', stats['outra_rm'], '| sem gestão:', stats['sem_gestao'], '| nota inválida:', stats['avaliacao_invalida'])
    if faltantes:
        print('  Bases sem match (top 10):', faltantes.most_common(10))
    for semana in sorted(semanas):
        total, sim = semanas[semana]['total'], semanas[semana]['sim']
        print(f'  {semana}: {total} avaliações | {sim} positivas | {total-sim} negativas | CSAT {100*sim/total:.2f}%')
    if not URL.startswith('https://') or not KEY:
        raise RuntimeError('Configure JT_API_URL HTTPS e JT_API_KEY no .env (sem publicar a chave).')
    with requests.Session() as sess:
        db = str(scalar(sess, 'SELECT current_database() AS nome'))
        print('JT API conectada ao PostgreSQL:', db)
        if db != 'jt_indicadores':
            raise RuntimeError('Banco errado: esperado jt_indicadores; gravação não permitida.')
        existe = int(scalar(sess, "SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema='public' AND table_name=%s", [TABELA]) or 0)>0
        if existe:
            colunas = {str((r.get('column_name') if isinstance(r,dict) else r[0]))
                       for r in query(sess, "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s", [TABELA])}
            faltam = set(CAMPOS)-colunas
            if faltam:
                raise RuntimeError(f'Colunas ausentes na tabela CSAT: {sorted(faltam)}. Não importar.')
            unico = int(scalar(sess, """SELECT COUNT(*) FROM pg_index i
                  JOIN pg_class t ON t.oid=i.indrelid JOIN pg_namespace n ON n.oid=t.relnamespace
                  JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum = ANY(i.indkey)
                  WHERE n.nspname='public' AND t.relname=%s AND i.indisunique
                    AND i.indisvalid AND i.indpred IS NULL AND i.indexprs IS NULL
                    AND i.indnkeyatts=1 AND a.attname='id'""", [TABELA]) or 0)
            if not unico:
                raise RuntimeError('CSAT já existe sem índice UNIQUE(id). Necessária correção no banco.')
            print('Esquema CSAT e UNIQUE(id): OK')
            print('Registros no PostgreSQL antes:',scalar(sess, f'SELECT COUNT(*) FROM public.{TABELA}'))
        else:
            print('Tabela CSAT ausente: será criada pelo /import se --aplicar for confirmado.')
        if not args.aplicar:
            print('AUDITORIA OK — SEM GRAVAÇÕES.')
            print('Para publicar: python publicar_csat_via_api.py --aplicar --confirmar-banco jt_indicadores')
            return
        if args.confirmar_banco != db:
            raise RuntimeError('Confirmação do banco divergente; publicação cancelada.')
        for start in range(0,len(rows),args.lote):
            part = rows[start:start+args.lote]
            post(sess,'/import',{
                'tabela':TABELA,'chave':['id'],'registros':part,
                'criar_tabela':not existe,'adicionar_colunas':False,
            })
            existe = True
            print(f'  enviados {start+len(part):,}/{len(rows):,}',flush=True)
        for semana, vals in sorted(semanas.items()):
            cnt = int(scalar(sess,f'SELECT COUNT(*) FROM public.{TABELA} WHERE semana_id=%s',[semana]) or 0)
            yes = int(scalar(sess,f'SELECT COUNT(*) FROM public.{TABELA} WHERE semana_id=%s AND avaliacao=1',[semana]) or 0)
            if cnt < vals['total'] or yes < vals['sim']:
                raise RuntimeError(f'{semana}: conferência divergente; PostgreSQL={cnt}/{yes} e arquivo={vals["total"]}/{vals["sim"]}.')
            print(f'  CONFERÊNCIA {semana}: {cnt} avaliações | {yes} positivas | {100*yes/cnt if cnt else 0:.2f}%')
        print('PUBLICAÇÃO CSAT CONCLUÍDA. 1BD, 5CD e Gestão NÃO foram alterados.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError) as exc:
        print('ERRO:', exc, file=sys.stderr)
        sys.exit(1)
