from __future__ import absolute_import, unicode_literals
import os
from django.http import HttpResponse, JsonResponse
from django.template import Context, Template
from django.utils.decorators import method_decorator
from django.views import View

from corehq import toggles
from corehq.apps.api.odata.utils import get_case_type_to_properties
from corehq.apps.app_manager.app_schemas.case_properties import ParentCasePropertyBuilder
from corehq.apps.app_manager.dbaccessors import get_apps_in_domain
from corehq.apps.domain.decorators import api_auth
from corehq.apps.reports.analytics.esaccessors import get_case_types_for_domain_es
from corehq.util.view_utils import absolute_reverse
from io import open


class ODataServiceView(View):

    @method_decorator(api_auth)
    @method_decorator(toggles.ODATA.required_decorator())
    def get(self, request, domain):
        data = {
            '@odata.context': absolute_reverse('odata_meta', args=[domain]),
            'value': [
                {
                    'name': case_type,
                    'kind': 'EntitySet',
                    'url': case_type,
                }
                for case_type in get_case_types_for_domain_es(domain)
            ]
        }
        return add_odata_headers(JsonResponse(data))


class ODataMetadataView(View):

    @method_decorator(api_auth)
    @method_decorator(toggles.ODATA.required_decorator())
    def get(self, request, domain):
        data_file = os.path.join(os.path.dirname(__file__), 'metadata.xml')
        with open(data_file, 'r') as f:
            metadata_template = Template(f.read())
        metadata = metadata_template.render(Context({
            'case_type_to_properties': get_case_type_to_properties(domain)
        }))
        return add_odata_headers(HttpResponse(metadata, content_type='application/xml'))


def add_odata_headers(response):
    response['OData-Version'] = '4.0'
    return response
