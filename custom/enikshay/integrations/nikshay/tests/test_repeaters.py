import json
from collections import namedtuple
from datetime import datetime
from django.test import TestCase

from corehq.apps.locations.tests.util import delete_all_locations
from corehq.form_processor.interfaces.dbaccessors import CaseAccessors
from corehq.util.test_utils import flag_enabled
from custom.enikshay.exceptions import RequiredValueMissing, NikshayLocationNotFound
from custom.enikshay.integrations.nikshay.repeaters import (
    NikshayRegisterPatientRepeater,
    NikshayFollowupRepeater,
)
from custom.enikshay.tests.utils import ENikshayCaseStructureMixin, ENikshayLocationStructureMixin

from custom.enikshay.integrations.nikshay.repeater_generator import (
    NikshayRegisterPatientPayloadGenerator,
    NikshayFollowupPayloadGenerator,
    NikshayHIVTestPayloadGenerator,
    ENIKSHAY_ID,
)
from corehq.form_processor.tests.utils import run_with_all_backends
from casexml.apps.case.mock import CaseStructure
from corehq.apps.repeaters.models import RepeatRecord
from corehq.apps.repeaters.dbaccessors import delete_all_repeat_records, delete_all_repeaters
from casexml.apps.case.tests.util import delete_all_cases
from custom.enikshay.case_utils import update_case


class MockResponse(object):
    def __init__(self, status_code, json_data):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data


class NikshayRepeaterTestBase(ENikshayCaseStructureMixin, TestCase):
    def setUp(self):
        super(NikshayRepeaterTestBase, self).setUp()

        delete_all_repeat_records()
        delete_all_repeaters()
        delete_all_cases()

    def tearDown(self):
        super(NikshayRepeaterTestBase, self).tearDown()

        delete_all_repeat_records()
        delete_all_repeaters()
        delete_all_cases()

    def repeat_records(self):
        return RepeatRecord.all(domain=self.domain, due_before=datetime.utcnow())

    def _create_nikshay_enabled_case(self, case_id=None):
        if case_id is None:
            case_id = self.episode_id

        nikshay_enabled_case_on_update = CaseStructure(
            case_id=case_id,
            attrs={
                "create": False,
                "update": dict(
                    episode_pending_registration='no',
                )
            }
        )

        return self.create_case(nikshay_enabled_case_on_update)[0]

    def _create_nikshay_registered_case(self):
        nikshay_registered_case = CaseStructure(
            case_id=self.episode_id,
            attrs={
                'create': False,
                "update": dict(
                    nikshay_registered='true',
                )
            }
        )
        self.create_case(nikshay_registered_case)


class TestNikshayRegisterPatientRepeater(NikshayRepeaterTestBase):

    def setUp(self):
        super(TestNikshayRegisterPatientRepeater, self).setUp()

        self.repeater = NikshayRegisterPatientRepeater(
            domain=self.domain,
            url='case-repeater-url',
            username='test-user'
        )
        self.repeater.white_listed_case_types = ['episode']
        self.repeater.save()

    def test_not_available_for_domain(self):
        self.assertFalse(NikshayRegisterPatientRepeater.available_for_domain(self.domain))

    @flag_enabled('NIKSHAY_INTEGRATION')
    def test_available_for_domain(self):
        self.assertTrue(NikshayRegisterPatientRepeater.available_for_domain(self.domain))

    @run_with_all_backends
    def test_trigger(self):
        # nikshay not enabled
        self.create_case(self.episode)
        self.assertEqual(0, len(self.repeat_records().all()))

        # nikshay enabled, should register a repeat record
        self._create_nikshay_enabled_case()
        self.assertEqual(1, len(self.repeat_records().all()))
        #
        # set as registered, should not register a new repeat record
        self._create_nikshay_registered_case()
        self.assertEqual(1, len(self.repeat_records().all()))

    @run_with_all_backends
    def test_trigger_different_case_type(self):
        # different case type
        self.create_case(self.person)
        self._create_nikshay_enabled_case(case_id=self.person_id)
        self.assertEqual(0, len(self.repeat_records().all()))


class TestNikshayRegisterPatientPayloadGenerator(ENikshayLocationStructureMixin, NikshayRepeaterTestBase):
    def setUp(self):
        super(TestNikshayRegisterPatientPayloadGenerator, self).setUp()
        self.cases = self.create_case_structure()
        self.assign_person_to_location(self.phi.location_id)

    @run_with_all_backends
    def test_payload_properties(self):
        episode_case = self._create_nikshay_enabled_case()
        payload = (json.loads(
            NikshayRegisterPatientPayloadGenerator(None).get_payload(None, episode_case))
        )
        self.assertEqual(payload['Source'], ENIKSHAY_ID)
        self.assertEqual(payload['Local_ID'], self.person_id)
        self.assertEqual(payload['regBy'], "tbu-dmdmo01")

        # From Person
        self.assertEqual(payload['pname'], "Peregrine Took")
        self.assertEqual(payload['page'], '20')
        self.assertEqual(payload['pgender'], 'M')
        self.assertEqual(payload['paddress'], 'Mr. Everest')
        self.assertEqual(payload['pmob'], self.primary_phone_number)
        self.assertEqual(payload['cname'], 'Mrs. Everestie')
        self.assertEqual(payload['caddress'], 'Mrs. Everestie')
        self.assertEqual(payload['cmob'], self.secondary_phone_number)
        self.assertEqual(payload['pcategory'], '2')

        # From Episode
        self.assertEqual(payload['sitedetail'], 2)
        self.assertEqual(payload['Ptype'], '6')
        self.assertEqual(payload['poccupation'], 4)
        self.assertEqual(payload['dotname'], 'Gandalf The Grey')
        self.assertEqual(payload['dotmob'], '066000666')
        self.assertEqual(payload['disease_classification'], 'EP')
        self.assertEqual(payload['pregdate'], '2014-09-09')
        self.assertEqual(payload['ptbyr'], '2014')
        self.assertEqual(payload['dotpType'], '5')
        self.assertEqual(payload['dotdesignation'], 'ngo_volunteer')
        self.assertEqual(payload['dateofInitiation'], '2015-03-03')

    def _assert_case_property_equal(self, case, case_property, expected_value):
        self.assertEqual(case.dynamic_case_properties().get(case_property), expected_value)

    @run_with_all_backends
    def test_handle_success(self):
        nikshay_id = "NIKSHAY!"
        self._create_nikshay_enabled_case()
        payload_generator = NikshayRegisterPatientPayloadGenerator(None)
        payload_generator.handle_success(
            MockResponse(
                201,
                {
                    "Nikshay_Message": "Success",
                    "Results": [
                        {
                            "FieldName": "NikshayId",
                            "Fieldvalue": nikshay_id,
                        }
                    ]
                }
            ),
            self.cases[self.episode_id],
            None,
        )
        updated_episode_case = CaseAccessors(self.domain).get_case(self.episode_id)
        self._assert_case_property_equal(updated_episode_case, 'nikshay_registered', 'true')
        self._assert_case_property_equal(updated_episode_case, 'nikshay_error', '')
        self._assert_case_property_equal(updated_episode_case, 'nikshay_id', nikshay_id)
        self.assertEqual(updated_episode_case.external_id, nikshay_id)

    @run_with_all_backends
    def test_handle_bad_nikshay_response(self):
        self._create_nikshay_enabled_case()
        payload_generator = NikshayRegisterPatientPayloadGenerator(None)
        response = {
            "Nikshay_Message": "Success",
            "Results": [
                {
                    "FieldName": "BadResponse",
                    "Fieldvalue": "Borked",
                }
            ]
        }
        payload_generator.handle_success(
            MockResponse(
                201,
                response,
            ),
            self.cases[self.episode_id],
            None,
        )
        updated_episode_case = CaseAccessors(self.domain).get_case(self.episode_id)
        self._assert_case_property_equal(updated_episode_case, 'nikshay_registered', 'false')
        self._assert_case_property_equal(
            updated_episode_case,
            'nikshay_error',
            'No Nikshay ID received: {}'.format(response)
        )

    @run_with_all_backends
    def test_handle_duplicate(self):
        payload_generator = NikshayRegisterPatientPayloadGenerator(None)
        payload_generator.handle_failure(
            MockResponse(
                409,
                {
                    "Nikshay_Message": "Conflict",
                    "Results": [
                        {
                            "FieldName": "NikshayId",
                            "Fieldvalue": "Dublicate Entry"
                        }
                    ]
                }
            ),
            self.cases[self.episode_id],
            None,
        )
        updated_episode_case = CaseAccessors(self.domain).get_case(self.episode_id)
        self._assert_case_property_equal(updated_episode_case, 'nikshay_registered', 'true')
        self._assert_case_property_equal(updated_episode_case, 'nikshay_error', 'duplicate')

    @run_with_all_backends
    def test_handle_failure(self):
        message = {
            "Nikshay_Message": "Success",
            "Results": [
                {
                    "FieldName": "NikshayId",
                    "Fieldvalue": "The INSERT statement conflicted with the FOREIGN KEY constraint \"FK_PatientsDetails_TBUnits\". The conflict occurred in database \"nikshay\", table \"dbo.TBUnits\".\u000d\u000a \u000d\u000aDM-ABC-01-16-0001\u000d\u000aThe statement has been terminated."  # noqa. yes, this is a real response.
                }
            ]
        }
        payload_generator = NikshayRegisterPatientPayloadGenerator(None)
        payload_generator.handle_failure(
            MockResponse(
                400,
                message,
            ),
            self.cases[self.episode_id],
            None,
        )
        updated_episode_case = CaseAccessors(self.domain).get_case(self.episode_id)
        self._assert_case_property_equal(updated_episode_case, 'nikshay_registered', 'false')
        self._assert_case_property_equal(updated_episode_case, 'nikshay_error', unicode(message))


class TestNikshayFollowupRepeater(ENikshayLocationStructureMixin, NikshayRepeaterTestBase):

    def setUp(self):
        super(TestNikshayFollowupRepeater, self).setUp()

        self.repeater = NikshayFollowupRepeater(
            domain=self.domain,
            url='case-repeater-url',
            username='test-user'
        )
        self.repeater.white_listed_case_types = ['test']
        self.repeater.save()

    def test_not_available_for_domain(self):
        self.assertFalse(NikshayFollowupRepeater.available_for_domain(self.domain))

    @flag_enabled('NIKSHAY_INTEGRATION')
    def test_available_for_domain(self):
        self.assertTrue(NikshayFollowupRepeater.available_for_domain(self.domain))

    @run_with_all_backends
    def test_trigger(self):
        self.assertEqual(0, len(self.repeat_records().all()))
        delete_all_locations()
        locations = self._setup_enikshay_locations(self.domain)
        self.dmc_location = locations['DMC']
        self.dmc_location.metadata['nikshay_code'] = 123
        self.dmc_location.save()

        self.factory.create_or_update_cases(
            [self.lab_referral, self.episode])
        update_case(
            self.domain,
            self.episode_id,
            {
                "nikshay_registered": 'true',
            },
        )
        # ToDo: This fails due to length in indices being 2
        # self.factory.create_or_update_cases([self.test])
        #
        # self.assertEqual(1, len(self.repeat_records().all()))


class TestNikshayFollowupPayloadGenerator(ENikshayLocationStructureMixin, NikshayRepeaterTestBase):
    def setUp(self):
        super(TestNikshayFollowupPayloadGenerator, self).setUp()
        delete_all_locations()
        locations = self._setup_enikshay_locations(self.domain)
        self.dmc_location = locations['DMC']
        self.dmc_location.metadata['nikshay_code'] = 123
        self.dmc_location.save()

        self.cases = self.create_case_structure()
        self.test_case = self.cases['test']

        self.dummy_nikshay_id = "MH-PRL-01-17-0054"
        self._create_nikshay_registered_case()

        MockRepeater = namedtuple('MockRepeater', 'username password')
        MockRepeatRecord = namedtuple('MockRepeatRecord', 'repeater')
        self.repeat_record = MockRepeatRecord(MockRepeater(username="arwen", password="Hadhafang"))

    def create_case_structure(self):
        return {case.get_id: case for case in filter(None, self.factory.create_or_update_cases(
            [self.lab_referral, self.test, self.episode]))}

    def _create_nikshay_registered_case(self):
        update_case(
            self.domain,
            self.episode_id,
            {
                "nikshay_id": self.dummy_nikshay_id,
            },
            external_id=self.dummy_nikshay_id,
        )

    @run_with_all_backends
    def test_payload_properties(self):
        payload = (json.loads(
            NikshayFollowupPayloadGenerator(None).get_payload(self.repeat_record, self.test_case))
        )
        self.assertEqual(payload['Source'], ENIKSHAY_ID)
        self.assertEqual(payload['Local_ID'], self.person_id)
        self.assertEqual(payload['RegBy'], "arwen")
        self.assertEqual(payload['password'], "Hadhafang")
        self.assertEqual(payload['IP_From'], "127.0.0.1")
        self.assertEqual(payload['TestDate'],
                         datetime.strptime(self.test_case.dynamic_case_properties().get('date_tested'),
                                           '%Y-%m-%d').strftime('%d/%m/%Y'),
                         )
        self.assertEqual(payload['LabNo'], self.test_case.dynamic_case_properties().get('lab_serial_number'))
        self.assertEqual(payload['IntervalId'], 0)
        self.assertEqual(payload['PatientWeight'], '40')
        self.assertEqual(payload["SmearResult"], 11)
        self.assertEqual(payload["DMC"], 123)
        self.assertEqual(payload["PatientID"], self.dummy_nikshay_id)

    @run_with_all_backends
    def test_intervalId(self):
        update_case(self.domain,
            self.test_id,
            {
                "purpose_of_testing": "testing",
                "follow_up_test_reason": "end_of_cp"
            },
            external_id=self.dummy_nikshay_id,
        )
        test_case = CaseAccessors(self.domain).get_case(self.test_id)
        payload = (json.loads(
            NikshayFollowupPayloadGenerator(None).get_payload(self.repeat_record, test_case))
        )
        self.assertEqual(payload['IntervalId'], 4)

    def test_mandatory_field_interval_id(self):
        update_case(self.domain,
                    self.test_id,
                    {
                        "purpose_of_testing": "testing",
                        "follow_up_test_reason": "unknown_reason"
                    },
                    external_id=self.dummy_nikshay_id,
                    )
        test_case = CaseAccessors(self.domain).get_case(self.test_id)

        # raises error when purpose_of_testing is not diagnostic and test reason is not known to system
        with self.assertRaisesMessage(RequiredValueMissing,
                                      "Value missing for intervalID, purpose_of_testing: {testing_purpose}, "
                                      "follow_up_test_reason: {follow_up_test_reason}".format(
                                        testing_purpose="testing",
                                        follow_up_test_reason="unknown_reason"
                                      )):
            NikshayFollowupPayloadGenerator(None).get_payload(self.repeat_record, test_case)

        # does not raise error with purpose_of_testing being diagnostic since test reason is not relevant
        update_case(self.domain,
                    self.test_id,
                    {
                        "purpose_of_testing": "diagnostic",
                        "follow_up_test_reason": "unknown_reason"
                    },
                    external_id=self.dummy_nikshay_id,
                    )
        test_case = CaseAccessors(self.domain).get_case(self.test_id)
        NikshayFollowupPayloadGenerator(None).get_payload(self.repeat_record, test_case)

    def test_mandatory_field_smear_result(self):
        update_case(self.domain,
                    self.test_id,
                    {
                        "result_grade": "999++"
                    },
                    )
        test_case = CaseAccessors(self.domain).get_case(self.test_id)

        with self.assertRaisesMessage(
                RequiredValueMissing,
                "Mandatory value missing in one of the following LabSerialNo: {lab_serial_number}, ResultGrade: "
                "{result_grade}"
                .format(
                    lab_serial_number=test_case.dynamic_case_properties().get('lab_serial_number'),
                    result_grade="999++")
                ):

            NikshayFollowupPayloadGenerator(None).get_payload(self.repeat_record, test_case)

    def test_mandatory_field_dmc_code(self):
        lab_referral_case = CaseAccessors(self.domain).get_case(self.lab_referral_id)

        # valid
        self.dmc_location.metadata['nikshay_code'] = "123"
        self.dmc_location.save()
        NikshayFollowupPayloadGenerator(None).get_payload(self.repeat_record, self.test_case)

        # invalid since nikshay_code needs to be a code
        self.dmc_location.metadata['nikshay_code'] = "BARACK-OBAMA"
        self.dmc_location.save()
        with self.assertRaisesMessage(
                RequiredValueMissing,
                "InAppt value for dmc, got value: BARACK-OBAMA"
        ):
            NikshayFollowupPayloadGenerator(None).get_payload(self.repeat_record, self.test_case)

        # missing location id as owner_id
        lab_referral_case.owner_id = ''
        lab_referral_case.save()
        with self.assertRaisesMessage(
                NikshayLocationNotFound,
                "Location with id: {location_id} not found."
                "This is the owner for lab referral with id: {lab_referral_case_id}"
                .format(location_id=lab_referral_case.owner_id,
                        lab_referral_case_id=lab_referral_case.case_id)
        ):
            NikshayFollowupPayloadGenerator(None).get_payload(self.repeat_record, self.test_case)

        # missing location
        lab_referral_case.owner_id = '123456'
        lab_referral_case.save()
        with self.assertRaisesMessage(
                NikshayLocationNotFound,
                "Location with id: {location_id} not found."
                "This is the owner for lab referral with id: {lab_referral_case_id}"
                .format(location_id=123456,
                        lab_referral_case_id=lab_referral_case.case_id)
        ):
            NikshayFollowupPayloadGenerator(None).get_payload(self.repeat_record, self.test_case)


class TestNikshayHIVTestPayloadGenerator(ENikshayLocationStructureMixin, NikshayRepeaterTestBase):
    def setUp(self):
        super(TestNikshayHIVTestPayloadGenerator, self).setUp()
        self.cases = self.create_case_structure()
        self.person_case = self.cases['person']
        self.set_up_person_case()
        self.person_case = CaseAccessors(self.domain).get_case(self.person_id)
        self.episode_case = self.cases['episode']

        self.dummy_nikshay_id = "MH-PRL-01-17-0054"
        self._create_nikshay_registered_case()
        MockRepeater = namedtuple('MockRepeater', 'username password')
        MockRepeatRecord = namedtuple('MockRepeatRecord', 'repeater')
        self.repeat_record = MockRepeatRecord(MockRepeater(username="arwen", password="Hadhafang"))

    def create_case_structure(self):
        return {case.get_id: case for case in filter(None, self.factory.create_or_update_cases(
            [self.person, self.episode]))}

    def set_up_person_case(self):
        update_case(
            self.domain, self.person_id,
            {
                "hiv_status": "reactive",
                "hiv_test_date": "2016-01-01",
                "cpt_initiation_date": "2016-01-02",
                "art_initiation_date": "2016-01-03",
                "art_initiated": "yes"
            }
        )

    def _create_nikshay_registered_case(self):
        update_case(
            self.domain,
            self.episode_id,
            {
                "nikshay_id": self.dummy_nikshay_id,
            },
            external_id=self.dummy_nikshay_id,
        )

    @run_with_all_backends
    def test_payload_properties(self):
        payload = (json.loads(
            NikshayHIVTestPayloadGenerator(None).get_payload(self.repeat_record, self.person_case))
        )

        self.assertEqual(payload['Source'], ENIKSHAY_ID)
        self.assertEqual(payload['regby'], "arwen")
        self.assertEqual(payload['password'], "Hadhafang")
        self.assertEqual(payload['IP_FROM'], "127.0.0.1")
        self.assertEqual(payload["PatientID"], self.dummy_nikshay_id)
        self.assertEqual(payload["HIVStatus"], "Pos")
        self.assertEqual(payload["HIVTestDate"], "01/01/2016")
        self.assertEqual(payload["CPTDeliverDate"], "02/01/2016")
        self.assertEqual(payload["InitiatedDate"], "03/01/2016")
        self.assertEqual(payload["ARTCentreDate"], "03/01/2016")
