import corehq.apps.app_manager.util as util
from corehq.apps.app_manager.const import APP_V2
from corehq.apps.app_manager.models import (
    Application,
    Module,
    OpenCaseAction,
    OpenSubCaseAction,
    AdvancedModule,
    FormSchedule,
    ScheduleVisit
)
from corehq.apps.app_manager.tests import TestXmlMixin, AppFactory
from django.test.testcases import SimpleTestCase
from mock import patch


class GetCasePropertiesTest(SimpleTestCase, TestXmlMixin):
    file_path = ('data',)

    def assertCaseProperties(self, app, case_type, expected_properties):
        properties = util.get_case_properties(app, [case_type])
        self.assertEqual(
            set(properties[case_type]),
            set(expected_properties),
        )

    def test_basic_apps(self):
        for class_ in (Module, AdvancedModule):
            factory = AppFactory()
            m1, m1f1 = factory.new_module(class_, 'open_case', 'house')
            factory.form_opens_case(m1f1)
            m1f2 = factory.new_form(m1)
            factory.form_requires_case(m1f2, case_type='house', update={
                'foo': '/data/question1',
                'bar': '/data/question2',
            })
            self.assertCaseProperties(factory.app, 'house', ['foo', 'bar'])

    def test_scheduler_module(self):
        factory = AppFactory()
        m1, m1f1 = factory.new_basic_module('open_case', 'house')
        factory.form_opens_case(m1f1)
        m2, m2f1 = factory.new_advanced_module('scheduler_module', 'house')
        m2f2 = factory.new_form(m2)
        factory.form_requires_case(m2f1, case_type='house', update={
            'foo': '/data/question1',
            'bar': '/data/question2',
        })
        factory.form_requires_case(m2f2, case_type='house', update={
            'bleep': '/data/question1',
            'bloop': '/data/question2',
        })

        self._add_scheduler_to_module(m2)
        self._add_scheduler_to_form(m2f1, m2, 'form1')
        self._add_scheduler_to_form(m2f2, m2, 'form2')

        self.assertCaseProperties(factory.app, 'house', [
            'foo',
            'bar',
            'bleep',
            'bloop',
            # Scheduler properties:
            'last_visit_date_form1',
            'last_visit_number_form1',
            'last_visit_date_form2',
            'last_visit_number_form2',
            'current_schedule_phase',
        ])

    def _add_scheduler_to_module(self, module):
        # (this mimics the behavior in app_manager.views.schedules.edit_schedule_phases()
        module.update_schedule_phase_anchors([(1, 'date-opened')])
        module.update_schedule_phases(['date-opened'])
        module.has_schedule = True

    def _add_scheduler_to_form(self, form, module, form_abreviation):
        # (this mimics the behavior in app_manager.views.schedules.edit_visit_schedule()
        # A Form.source is required to retreive scheduler properties
        form.source = self.get_xml('very_simple_form')
        phase, _ = module.get_or_create_schedule_phase(anchor='date-opened')
        form.schedule_form_id = form_abreviation
        form.schedule = FormSchedule(
            starts=5,
            expires=None,
            visits=[
                ScheduleVisit(due=7, expires=5, starts=-2),
            ]
        )
        phase.add_form(form)


class SchemaTest(SimpleTestCase):

    def setUp(self):
        self.models_is_usercase_in_use_patch = patch('corehq.apps.app_manager.models.is_usercase_in_use')
        self.models_is_usercase_in_use_mock = self.models_is_usercase_in_use_patch.start()
        self.models_is_usercase_in_use_mock.return_value = False
        self.util_is_usercase_in_use_patch = patch('corehq.apps.app_manager.util.is_usercase_in_use')
        self.util_is_usercase_in_use_mock = self.util_is_usercase_in_use_patch.start()
        self.util_is_usercase_in_use_mock.return_value = False

    def tearDown(self):
        self.models_is_usercase_in_use_patch.stop()
        self.util_is_usercase_in_use_patch.stop()

    def test_get_casedb_schema_empty_app(self):
        app = self.make_app()
        schema = util.get_casedb_schema(app)
        self.assert_has_kv_pairs(schema, {
            "id": "casedb",
            "uri": "jr://instance/casedb",
            "name": "case",
            "path": "/casedb/case",
            "structure": {},
            "subsets": [],
        })

    def test_get_casedb_schema_with_form(self):
        app = self.make_app()
        self.add_form(app, "village")
        schema = util.get_casedb_schema(app)
        self.assertEqual(len(schema["subsets"]), 1, schema["subsets"])
        self.assert_has_kv_pairs(schema["subsets"][0], {
            'id': 'village',
            'key': '@case_type',
            'structure': {'case_name': {}},
            'related': None,
        })

    def test_get_casedb_schema_with_related_case_types(self):
        app = self.make_app()
        self.add_form(app, "family")
        village = self.add_form(app, "village")
        village.actions.subcases.append(OpenSubCaseAction(
            case_type='family',
            reference_id='parent'
        ))
        schema = util.get_casedb_schema(app)
        subsets = {s["id"]: s for s in schema["subsets"]}
        self.assertEqual(subsets["village"]["related"], None)
        self.assertDictEqual(subsets["family"]["related"], {"parent": "village"})

    def test_get_session_schema_for_module_with_no_case_type(self):
        app = self.make_app()
        form = self.add_form(app)
        schema = util.get_session_schema(form)
        self.assert_has_kv_pairs(schema, {
            "id": "commcaresession",
            "uri": "jr://instance/session",
            "name": "Session",
            "path": "/session/data",
        })
        assert "case_id" not in schema["structure"], schema["structure"]

    def test_get_session_schema_for_simple_module_with_case(self):
        app = self.make_app()
        form = self.add_form(app, "village")
        schema = util.get_session_schema(form)
        self.assertDictEqual(schema["structure"]["case_id"], {
            "reference": {
                "source": "casedb",
                "subset": "village",
                "key": "@case_id",
            },
        })

    # -- helpers --

    def assert_has_kv_pairs(self, test_dict, expected_dict):
        """Assert that test_dict contains all key/value pairs in expected_dict

        Key/value pairs in `test_dict` but not present in
        `expected_dict` will be ignored.
        """
        for key, value in expected_dict.items():
            self.assertEqual(test_dict[key], value)

    def add_form(self, app, case_type=None, module_id=None):
        if module_id is None:
            module_id = len(app.modules)
            m = app.add_module(Module.new_module('Module{}'.format(module_id), lang='en'))
            if case_type:
                m.case_type = case_type
        form = app.new_form(module_id, 'form {}'.format(case_type), lang='en')
        if case_type:
            form.actions.open_case = OpenCaseAction(name_path="/data/question1", external_id=None)
            form.actions.open_case.condition.type = 'always'
        return form

    def make_app(self):
        app = Application.new_app('domain', 'New App', APP_V2)
        app.version = 1
        return app
