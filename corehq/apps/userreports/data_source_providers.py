from __future__ import absolute_import
from abc import ABCMeta, abstractmethod
from corehq.apps.userreports.models import DataSourceConfiguration, StaticDataSourceConfiguration
import six


class DataSourceProvider(six.with_metaclass(ABCMeta, object)):
    @abstractmethod
    def get_data_sources(self):
        pass


class DynamicDataSourceProvider(DataSourceProvider):

    def get_data_sources(self):
        return [DataSourceConfiguration.wrap(r['doc'])
                for r in
                DataSourceConfiguration.get_db().view('userreports/active_data_sources',
                                                      reduce=False, include_docs=True)]


class StaticDataSourceProvider(DataSourceProvider):

    def get_data_sources(self):
        return StaticDataSourceConfiguration.all()


class MockDataSourceProvider(DataSourceProvider):
    # for testing only

    def get_data_sources(self):
        return []
