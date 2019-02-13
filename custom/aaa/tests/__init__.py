from __future__ import absolute_import, unicode_literals

import os

import postgres_copy
import six
import sqlalchemy
from django.test.utils import override_settings

from corehq.apps.userreports.models import StaticDataSourceConfiguration
from corehq.apps.userreports.util import get_indicator_adapter
from corehq.sql_db.connections import connection_manager


FILE_NAME_TO_TABLE_MAPPING = {
    'child': 'config_report_reach-test_reach-child_health_cases_10a84c1d',
    'person': 'config_report_reach-test_reach-person_cases_26a9647f',
}


def setUpModule():
    with override_settings(SERVER_ENVIRONMENT='icds'):
        configs = StaticDataSourceConfiguration.by_domain('reach-test')
        adapters = [get_indicator_adapter(config) for config in configs]

        for adapter in adapters:
            try:
                adapter.drop_table()
            except Exception:
                pass
            adapter.build_table()

        engine = connection_manager.get_engine('default')
        metadata = sqlalchemy.MetaData(bind=engine)
        metadata.reflect(bind=engine, extend_existing=True)
        path = os.path.join(os.path.dirname(__file__), 'fixtures')

        for file_name in os.listdir(path):
            with open(os.path.join(path, file_name), encoding='utf-8') as f:
                table_name = FILE_NAME_TO_TABLE_MAPPING[file_name[:-4]]
                table = metadata.tables[table_name]
                columns = [
                    '"{}"'.format(c.strip())  # quote to preserve case
                    for c in f.readline().split(',')
                ]
                postgres_copy.copy_from(
                    f, table, engine, format='csv' if six.PY3 else b'csv',
                    null='' if six.PY3 else b'', columns=columns
                )


def tearDownModule():
    with override_settings(SERVER_ENVIRONMENT='icds'):
        configs = StaticDataSourceConfiguration.by_domain('reach-test')
        adapters = [get_indicator_adapter(config) for config in configs]
        for adapter in adapters:
            adapter.drop_table()
