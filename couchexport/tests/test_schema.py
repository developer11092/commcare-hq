from couchdbkit.ext.django.loading import get_db
from django.test import TestCase
from couchexport.export import SCALAR_NEVER_WAS
from couchexport.models import ExportSchema, SavedExportSchema, SplitColumn
from datetime import datetime, timedelta
from couchexport.util import SerializableFunction
from dimagi.utils.couch.database import get_safe_write_kwargs
import json
from couchexport.models import Format


class ExportSchemaTest(TestCase):

    def testSaveAndLoad(self):
        index = ["foo", 2]
        schema = ExportSchema(index=index, timestamp=datetime.now())
        inner = {"dict": {"bar": 1, "baz": [2,3]},
                 "list": ["foo", "bar"],
                 "dictlist": [{"bip": 1, "bop": "blah"},
                              {"bip": 2, "bop": "blah2"}],
                 "item": "yoyoyo"}
        schema.schema = inner
        schema.save()
        back = ExportSchema.get(schema.get_id)
        self.assertEqual(inner, back.schema)
        self.assertEqual(index, back.index)

    def testGetLast(self):
        indices = ["a string", ["a", "list"]]
        save_args = get_safe_write_kwargs()

        for index in indices:
            self.assertEqual(None, ExportSchema.last(index))
            dt = datetime.utcnow()
            schema1 = ExportSchema(index=index, timestamp=dt)
            schema1.save(**save_args)
            self.assertEqual(schema1._id, ExportSchema.last(index)._id)
            schema2 = ExportSchema(index=index, timestamp=dt + timedelta(seconds=1))
            schema2.save(**save_args)
            self.assertEqual(schema2._id, ExportSchema.last(index)._id)
            schema3 = ExportSchema(index=index, timestamp=dt - timedelta(seconds=1))
            schema3.save(**save_args)
            self.assertEqual(schema2._id, ExportSchema.last(index)._id)


class SavedSchemaTest(TestCase):
    def setUp(self):
        self.db = get_db('couchexport')
        self.custom_export = SavedExportSchema.wrap({
            'type': 'demo',
            'default_format': Format.JSON,
            'index': json.dumps(['test_custom']),
            'tables': [{
                'index': '#',
                'display': 'Export',
                'columns': [
                    {'index': 'multi', 'display': 'Split', 'doc_type': 'SplitColumn', 'options': ['a', 'b', 'c', 'd']}
                ],
            }]
        })
        self.custom_export.filter_function = SerializableFunction()
        self.schema = [{'#export_tag': [u'string'], 'tag': u'string', 'multi': u'string'}]

    def tearDown(self):
        for doc in self.db.all_docs():
            if not doc['id'].startswith('_design'):
                self.db.delete_doc(doc['id'])

    def post_it(self, **kwargs):
        doc = {'#export_tag': 'tag', 'tag': 'test_custom'}
        doc.update(kwargs)
        self.db.save_doc(doc, **get_safe_write_kwargs())

    def _test_split_column(self, rows, ignore_extras=False):
        self.custom_export.tables_by_index['#'].columns[0].ignore_extras = ignore_extras
        files = self.custom_export.get_export_files()
        data = json.loads(files.file.payload)
        expected_headers = ['Split | a', 'Split | b', 'Split | c', 'Split | d']
        if not ignore_extras:
            expected_headers += ['Split | extra']
        self.assertEqual(data['Export']['headers'], expected_headers)
        export_rows = data['Export']['rows']
        self.assertEqual(len(export_rows), len(rows))
        tuple_rows = {tuple(r) for r in export_rows}
        if len(tuple_rows) != len(export_rows):
            raise Exception("These tests require rows to be unique since ordering cannot be guaranteed")

        for row in rows:
            self.assertIn(tuple(row), tuple_rows)

    def test_split_column(self):
        self.post_it(multi='a b c d')
        self._test_split_column([[1, 1, 1, 1, None]])

    def test_split_column_order(self):
        self.post_it(multi='c d a')
        self._test_split_column([[1, None, 1, 1, None]])

    def test_split_column_empty(self):
        self.post_it(multi='')
        self._test_split_column([[None, None, None, None, None]])

    def test_split_column_None(self):
        self.post_it(multi=None)
        self._test_split_column([[None, None, None, None, None]])

    def test_split_column_ignore_extras(self):
        self.post_it(multi='d e f')
        self._test_split_column([[None, None, None, 1]], ignore_extras=True)

    def test_split_column_missing(self):
        self.post_it()
        self._test_split_column([[None, None, None, None, None]])

    def test_split_column_missing_ignore_extras(self):
        self.post_it()
        self._test_split_column([[None, None, None, None]], ignore_extras=True)

    def test_split_column_None_ignore_extras(self):
        self.post_it(multi=None)
        self._test_split_column([[None, None, None, None]], ignore_extras=True)

    def test_split_column_fit_to_schema_None(self):
        self.post_it(multi='a b c')
        self.post_it(multi=None)
        self._test_split_column(
            [
                [1, 1, 1, None],
                [None, None, None, None],
            ],
            ignore_extras=True
        )

    def test_split_column_fit_to_schema_missing(self):
        self.post_it(multi='a b c')
        self.post_it()
        self._test_split_column(
            [
                [1, 1, 1, None],
                [SCALAR_NEVER_WAS] * 4,
            ],
            ignore_extras=True
        )

    def test_split_column_remainder(self):
        self.post_it(multi='c b d e f g')
        self._test_split_column([[None, 1, 1, 1, 'e f g']])

    def test_split_column_header_format(self):
        col = SplitColumn(display='test_{option}', options=['a', 'b', 'c'])
        self.assertEqual(
            list(col.get_headers()),
            ['test_a', 'test_b', 'test_c', 'test_extra']
        )

    def test_split_column_not_string(self):
        col = SplitColumn(display='test_{option}', options=['a', 'b'])
        self.assertEqual(
            col.get_data(1),
            [None, None, 1]
        )
