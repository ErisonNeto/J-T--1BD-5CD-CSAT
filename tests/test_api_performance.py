"""Regressoes de paginacao e filtros do Painel de Qualidade.

Nao exige banco, VM, Render nem segredos em ambiente de CI.
"""
import os
import unittest
from unittest.mock import patch

import database
import main
import indicador_5cd
import indicador_csat


class ApiPaginationTests(unittest.TestCase):
    def setUp(self):
        database._cached_api_rows.cache_clear()

    def tearDown(self):
        database._cached_api_rows.cache_clear()

    def test_pagination_does_not_truncate_when_server_caps_results(self):
        expected = [{'id': i} for i in range(1201)]
        offsets = []

        def request(sql, params, columns):
            limit, offset = params[-2:]
            offsets.append(offset)
            # Simula uma JT API antiga que retorna no maximo 500 linhas
            return expected[offset:offset + min(limit, 500)]

        with patch.object(database, '_api_post_query', side_effect=request):
            with patch.dict(os.environ, {'JT_API_PAGE_SIZE': '2000'}):
                actual = database._cached_api_rows(
                    'SELECT id FROM testes ORDER BY id', (), ('id',), 42)
        self.assertEqual(actual, tuple(expected))
        self.assertEqual(offsets, [0, 500, 1000, 1201])

    def test_pagination_uses_larger_batches_if_supported(self):
        expected = [{'id': i} for i in range(2500)]
        offsets = []

        def request(sql, params, columns):
            limit, offset = params[-2:]
            offsets.append(offset)
            return expected[offset:offset + limit]

        with patch.object(database, '_api_post_query', side_effect=request):
            with patch.dict(os.environ, {'JT_API_PAGE_SIZE': '2000'}):
                actual = database._cached_api_rows(
                    'SELECT id FROM testes ORDER BY id', (), ('id',), 43)
        self.assertEqual(actual, tuple(expected))
        self.assertEqual(offsets, [0, 2000, 2500])

    def test_count_uses_one_request_without_pagination(self):
        with patch.object(database, '_api_post_query', return_value=[{'n': 19}]) as request:
            actual = database._cached_api_rows(
                'SELECT COUNT(*) AS n FROM jt_1bd_registros', (), ('n',), 44)
        self.assertEqual(actual, ({'n': 19},))
        request.assert_called_once()

    def test_positional_rows_map_to_explicit_columns(self):
        result = database._response_rows([['BASE A', 'PA', 'SC A']], ('base', 'uf', 'sc'))
        self.assertEqual(result, [{'base': 'BASE A', 'uf': 'PA', 'sc': 'SC A'}])


class FiltersTests(unittest.TestCase):
    def setUp(self):
        self.base_rows = [
            {'base': 'BASE A', 'uf': 'PA', 'sc': 'S/C A'},
            {'base': 'BASE B', 'uf': 'PA', 'sc': 'S/C B'},
            {'base': 'BASE C', 'uf': 'AM', 'sc': 'S/C C'},
        ]

    def test_1bd_filters_preserve_uf_sc_and_base(self):
        with patch.object(main, 'setup'), patch.object(main, 'rows', return_value=self.base_rows) as query:
            result = main.filtros(uf='PA', sc='S/C A')
        self.assertEqual(result['ufs'], ['AM', 'PA'])
        self.assertEqual(result['scs'], ['S/C A', 'S/C B'])
        self.assertEqual(result['bases'], [{'nome': 'BASE A', 'uf': 'PA'}])
        self.assertIn('DISTINCT', query.call_args.args[0])

    def test_5cd_filters_preserve_uf_sc_and_base(self):
        with patch.object(indicador_5cd, 'setup_5cd'), patch.object(
            indicador_5cd, 'rows', return_value=self.base_rows
        ):
            result = indicador_5cd.filtros(uf='PA', sc='S/C B')
        self.assertEqual(result['scs'], ['S/C A', 'S/C B'])
        self.assertEqual(result['bases'], [{'nome': 'BASE B', 'uf': 'PA'}])

    def test_csat_options_use_only_five_fields(self):
        rows = [{
            'semana_id': '2026-W45', 'semana_descricao': 'W45',
            'uf': 'PA', 'sc': 'S/C A', 'base': 'BASE A'
        }]
        with patch.object(indicador_csat, 'dados', return_value=rows) as source:
            result = indicador_csat.filtros(uf='PA')
        source.assert_called_once_with(somente_filtros=True)
        self.assertEqual(result['semanas'][0]['id'], '2026-W45')
        self.assertEqual(result['bases'], [{'nome': 'BASE A', 'uf': 'PA'}])


if __name__ == '__main__':
    unittest.main()
