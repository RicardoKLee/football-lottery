"""Current structural contract; synthetic declarations are not source evidence."""
import copy
import json
import re
from pathlib import Path
import unittest

from test_scripts import contracts, make_prediction, make_odds_snapshot

try:
    import jsonschema
except ImportError:
    jsonschema = None

ROOT = Path(__file__).resolve().parents[1]


TIME_CASES = [
    ('2026-08-25T08:00:00Z', True),
    ('2026-08-25T08:00:00+08:00', True),
    ('2026-08-25T08:00:00-05:30', True),
    ('2026-08-25t08:00:00.123z', True),
    ('2026-08-25T08:00:00', False),
    ('2026-08-25', False),
    ('2026-08-25 08:00:00+08:00', False),
    ('20260825T080000Z', False),
    ('2026-08-25T08:00Z', False),
    ('2026-08-25T08:00:00+0800', False),
    ('2026-08-25T08:00:00+08:00:30', False),
    ('2026-08-25T08:00:00+08:60', False),
    ('2026-02-30T08:00:00Z', False),
    ('2026-08-25T24:00:00Z', False),
    ('2026-08-25T08:00:00Z\n', False),
    (' 2026-08-25T08:00:00Z', False),
]
ID_CASES = [(value, valid) for value, valid in [
    ('fixture:1', True), ('alpha:beta:1', True),
    ('fixture:1\n', False), ('fixture:1\r', False),
    ('fixture:1\r\n', False), ('fixture:1 2', False),
    ('fixture:1\t2', False), ('fixture:\n1', False),
    (' fixture:1', False), ('fixture:', False), (':1', False),
]]


def boundary_cases(factory, paths, replacements):
    cases = []
    for path in paths:
        for replacement, valid in replacements:
            value = factory()
            parent = value
            for key in path[:-1]:
                parent = parent[key]
            parent[path[-1]] = replacement
            cases.append((f'{path}: {replacement!r}', value, valid))
    return cases


def prediction_cases():
    cases = []
    for code in ('J1', 'CUP-X', 'INT-X'):
        value = make_prediction()
        value['match']['competition_code'] = code
        cases.append((code, value, True))
    mutations = [
        ('blank_code', ('match', 'competition_code'), '  '),
        ('bad_context', ('match', 'context'), []),
        ('team_type', ('match', 'context', 'team_type'), 'youth'),
        ('competition_type', ('match', 'context', 'competition_type'), 'friendly'),
        ('venue', ('match', 'context', 'venue'), 'away'),
        ('score_basis', ('match', 'context', 'score_basis'), 'fullTime'),
        ('unqualified_team', ('match', 'home_team', 'team_id'), '65'),
        ('unqualified_match', ('match', 'match_id'), '1001'),
        ('empty_provider_id', ('match', 'home_team', 'team_id'), ' :65'),
        ('provenance', ('data_snapshot', 'provenance_status'), 'trusted'),
        ('empty_pool', ('data_snapshot', 'sample_pool'), {}),
        ('pool_id', ('data_snapshot', 'sample_pool', 'pool_id'), ' '),
        ('pool_type', ('data_snapshot', 'sample_pool', 'team_type'), 'mixed'),
        ('pool_codes', ('data_snapshot', 'sample_pool', 'competition_codes'), []),
        ('blank_pool_code', ('data_snapshot', 'sample_pool', 'competition_codes'), [' ']),
        ('quality', ('quality', 'status'), 'good'),
    ]
    for name, path, replacement in mutations:
        value = make_prediction()
        parent = value
        for key in path[:-1]:
            parent = parent[key]
        parent[path[-1]] = replacement
        cases.append((name, value, False))
    for path in [('match', 'context'), ('data_snapshot', 'provenance_status'), ('data_snapshot', 'sample_pool')]:
        value = make_prediction()
        del value[path[0]][path[1]]
        cases.append(('missing_' + path[1], value, False))
    cases.extend(boundary_cases(make_prediction, [
        ('match', 'kickoff_utc'), ('data_snapshot', 'fetched_at'),
    ], TIME_CASES))
    cases.extend(boundary_cases(make_prediction, [
        ('match', 'match_id'), ('match', 'home_team', 'team_id'),
        ('match', 'away_team', 'team_id'),
    ], ID_CASES))
    return cases


def odds_cases():
    cases = [('valid', make_odds_snapshot(), True)]
    for field in ('official_listing', 'market_status'):
        value = make_odds_snapshot()
        del value['matches'][0][field]
        cases.append(('missing_' + field, value, False))
    for field, key, bad in [('official_listing', 'status', 'open'),
                            ('official_listing', 'source_url', ' '),
                            ('official_listing', 'observed_at', ''),
                            ('official_listing', 'provider_match_id', ''),
                            ('market_status', 'had', 'selling')]:
        value = make_odds_snapshot()
        value['matches'][0][field][key] = bad
        cases.append((field + key, value, False))
    value = make_odds_snapshot()
    del value['matches'][0]['market_status']['had']
    cases.append(('missing_had_status', value, False))
    cases.extend(boundary_cases(make_odds_snapshot, [
        ('fetched_at',), ('matches', 0, 'kickoff_utc'),
        ('matches', 0, 'cutoff_utc'), ('matches', 0, 'odds_observed_at'),
        ('matches', 0, 'official_listing', 'observed_at'),
    ], TIME_CASES))
    cases.extend(boundary_cases(make_odds_snapshot, [('matches', 0, 'match_id')], ID_CASES))
    return cases


class ScopeContextTests(unittest.TestCase):
    def test_unknown_venue_is_not_home(self):
        from match_context import context_reasons
        self.assertIn('venue_unknown', context_reasons(dict(team_type='national', competition_type='cup',
                                                          venue='unknown', score_basis='regulation')))

    def test_ids_do_not_collide(self):
        from match_context import stable_id
        self.assertNotEqual(stable_id('alpha', '1'), stable_id('beta', '1'))
        self.assertEqual(stable_id('alpha', 'beta:1'), 'alpha:beta:1')
        for provider, entity in [('', '1'), (' ', '1'), ('a', ''), ('a', ' '), (None, '1'), ('a', 1), ('a:b', '1')]:
            with self.subTest(provider=provider, entity=entity), self.assertRaises(ValueError):
                stable_id(provider, entity)

    def test_context_enums_and_missing_fields(self):
        from match_context import validate_context, context_reasons
        context = dict(team_type='national', competition_type='cup', venue='neutral', score_basis='regulation')
        self.assertIs(validate_context(context), context)
        self.assertEqual(context_reasons(context), [])
        unknown = dict.fromkeys(context, 'unknown')
        self.assertEqual(set(context_reasons(unknown)), {'team_type_unknown', 'competition_type_unknown', 'venue_unknown', 'score_basis_unknown'})
        for key in context:
            for bad in ('', ' ', [], None, 'invalid'):
                value = dict(context, **{key: bad})
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    validate_context(value)
            value = dict(context)
            del value[key]
            with self.assertRaises(ValueError):
                validate_context(value)

    def test_current_prediction_contract(self):
        for name, value, valid in prediction_cases():
            with self.subTest(name=name):
                if valid:
                    self.assertIs(contracts.validate_model_prediction(value), value)
                else:
                    with self.assertRaises(contracts.ContractError):
                        contracts.validate_model_prediction(value)

    def test_missing_context_cannot_be_bypassed_by_metadata(self):
        value = make_prediction()
        del value['match']['context']
        value['schema_version'] = '2.0'
        with self.assertRaises(contracts.ContractError):
            contracts.validate_model_prediction(value)

    def test_validation_does_not_promote_source_declarations(self):
        value = make_prediction()
        before = copy.deepcopy(value)
        contracts.validate_model_prediction(value)
        self.assertEqual(value, before)
        self.assertEqual(value['data_snapshot']['provenance_status'], 'unverified')

    def test_current_odds_contract(self):
        for name, value, valid in odds_cases():
            with self.subTest(name=name):
                if valid:
                    self.assertIs(contracts.validate_odds_snapshot(value), value)
                else:
                    with self.assertRaises(contracts.ContractError):
                        contracts.validate_odds_snapshot(value)

    def test_schema_id_patterns_reject_whitespace(self):
        # Exercise the actual Schema patterns with search semantics even when
        # jsonschema is unavailable; this is not full Schema validation.
        prediction = json.loads(ROOT.joinpath('schemas/model-prediction.schema.json').read_text())
        odds = json.loads(ROOT.joinpath('schemas/odds-snapshot.schema.json').read_text())
        fields = [prediction['properties']['match']['properties']['match_id'],
                  prediction['$defs']['team']['properties']['team_id'],
                  odds['properties']['matches']['items']['properties']['match_id']]
        for index, field in enumerate(fields):
            for value, valid in ID_CASES:
                with self.subTest(field=index, value=value):
                    self.assertEqual(re.search(field['pattern'], value) is not None, valid)

    @unittest.skipIf(jsonschema is None, 'jsonschema not installed; no dependency installation authorized')
    def test_schemas_against_same_fixtures(self):
        for filename in ROOT.joinpath('schemas').glob('*.schema.json'):
            jsonschema.Draft202012Validator.check_schema(json.loads(filename.read_text()))
        for filename, cases in [('model-prediction', prediction_cases()), ('odds-snapshot', odds_cases())]:
            schema = json.loads(ROOT.joinpath('schemas', filename + '.schema.json').read_text())
            validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
            for name, value, valid in cases:
                with self.subTest(schema=filename, name=name):
                    self.assertEqual(validator.is_valid(value), valid)
