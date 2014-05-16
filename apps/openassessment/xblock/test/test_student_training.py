# -*- coding: utf-8 -*-
"""
Tests for the student training step in the Open Assessment XBlock.
"""
import datetime
import ddt
import json
from mock import patch
import pytz
from django.db import DatabaseError
from openassessment.assessment.models import StudentTrainingWorkflow
from .base import XBlockHandlerTestCase, scenario

@ddt.ddt
class StudentTrainingAssessTest(XBlockHandlerTestCase):
    """
    Tests for student training assessment.
    """
    SUBMISSION = {
        'submission': u'Thé őbjéćt őf édúćátíőń íś tő téáćh úś tő ĺővé ẃhát íś béáútífúĺ.'
    }

    @scenario('data/student_training.xml', user_id="Plato")
    @ddt.file_data('data/student_training_mixin.json')
    def test_correct(self, xblock, data):
        xblock.create_submission(xblock.get_student_item_dict(), self.SUBMISSION)
        self._assert_path_and_context(xblock, data["expected_template"], data["expected_context"])

        # Agree with the course author's assessment
        # (as defined in the scenario XML)
        data = {
            'options_selected': {
                'Vocabulary': 'Good',
                'Grammar': 'Excellent'
            }
        }
        resp = self.request(xblock, 'training_assess', json.dumps(data), response_format='json')

        # Expect that we were correct
        self.assertTrue(resp['success'], msg=resp.get('msg'))
        self.assertTrue(resp['correct'])

    @scenario('data/student_training.xml', user_id="Plato")
    @ddt.file_data('data/student_training_mixin.json')
    def test_incorrect(self, xblock, data):
        xblock.create_submission(xblock.get_student_item_dict(), self.SUBMISSION)
        self._assert_path_and_context(xblock, data["expected_template"], data["expected_context"])

        # Disagree with the course author's assessment
        # (as defined in the scenario XML)
        select_data = {
            'options_selected': {
                'Vocabulary': 'Poor',
                'Grammar': 'Poor'
            }
        }
        resp = self.request(xblock, 'training_assess', json.dumps(select_data), response_format='json')

        # Expect that we were marked incorrect
        self.assertTrue(resp['success'], msg=resp.get('msg'))
        self.assertFalse(resp['correct'])

    @scenario('data/student_training.xml', user_id="Plato")
    @ddt.file_data('data/student_training_mixin.json')
    def test_updates_workflow(self, xblock, data):
        expected_context = data["expected_context"].copy()
        expected_template = data["expected_template"]
        xblock.create_submission(xblock.get_student_item_dict(), self.SUBMISSION)
        self._assert_path_and_context(xblock, expected_template, expected_context)

        # Agree with the course author's assessment
        # (as defined in the scenario XML)
        selected_data = {
            'options_selected': {
                'Vocabulary': 'Good',
                'Grammar': 'Excellent'
            }
        }
        resp = self.request(xblock, 'training_assess', json.dumps(selected_data), response_format='json')

        # Expect that we were correct
        self.assertTrue(resp['success'], msg=resp.get('msg'))
        self.assertTrue(resp['correct'])

        # Agree with the course author's assessment
        # (as defined in the scenario XML)
        selected_data = {
            'options_selected': {
                'Vocabulary': 'Excellent',
                'Grammar': 'Poor'
            }
        }

        expected_context["training_num_completed"] = 1
        expected_context["training_essay"] = u"тєѕт αηѕωєя"
        self._assert_path_and_context(xblock, expected_template, expected_context)
        resp = self.request(xblock, 'training_assess', json.dumps(selected_data), response_format='json')

        # Expect that we were correct
        self.assertTrue(resp['success'], msg=resp.get('msg'))
        self.assertTrue(resp['correct'])
        expected_context = {}
        expected_template = "openassessmentblock/student_training/student_training_complete.html"
        self._assert_path_and_context(xblock, expected_template, expected_context)

    @scenario('data/student_training.xml', user_id="Plato")
    @ddt.file_data('data/student_training_mixin.json')
    def test_request_error(self, xblock, data):
        xblock.create_submission(xblock.get_student_item_dict(), self.SUBMISSION)
        expected_context = data["expected_context"].copy()
        expected_template = data["expected_template"]
        self._assert_path_and_context(xblock, expected_template, expected_context)
        resp = self.request(xblock, 'training_assess', json.dumps({}), response_format='json')
        self.assertFalse(resp['success'], msg=resp.get('msg'))

        selected_data = {
            'options_selected': "foo"
        }
        resp = self.request(xblock, 'training_assess', json.dumps(selected_data), response_format='json')
        self.assertFalse(resp['success'], msg=resp.get('msg'))

    @scenario('data/student_training.xml', user_id="Plato")
    @ddt.file_data('data/student_training_mixin.json')
    def test_invalid_options_dict(self, xblock, data):
        xblock.create_submission(xblock.get_student_item_dict(), self.SUBMISSION)
        expected_context = data["expected_context"].copy()
        expected_template = data["expected_template"]
        self._assert_path_and_context(xblock, expected_template, expected_context)

        selected_data = {
            'options_selected': {
                'Bananas': 'Excellent',
                'Grammar': 'Poor'
            }
        }

        resp = self.request(xblock, 'training_assess', json.dumps(selected_data), response_format='json')
        self.assertFalse(resp['success'], msg=resp.get('msg'))

    @scenario('data/student_training.xml', user_id="Plato")
    def test_no_submission(self, xblock):
        selected_data = {
            'options_selected': {
                'Vocabulary': 'Excellent',
                'Grammar': 'Poor'
            }
        }
        resp = self.request(xblock, 'training_assess', json.dumps(selected_data))
        self.assertIn("Your scores could not be checked", resp.decode('utf-8'))

    def _assert_path_and_context(self, xblock, expected_path, expected_context):
        """
        Render the student training step and verify that the expected template
        and context were used.  Also check that the template renders without error.

        Args:
            xblock (OpenAssessmentBlock): The XBlock under test.
            expected_path (str): The expected template path.
            expected_context (dict): The expected template context.

        Raises:
            AssertionError

        """
        path, context = xblock.training_path_and_context()
        self.assertEqual(path, expected_path)
        self.assertEqual(len(context), len(expected_context))
        [self.assertEqual(context[key], expected_context[key]) for key in expected_context.keys()]

        # Verify that we render without error
        resp = self.request(xblock, 'render_student_training', json.dumps({}))
        self.assertGreater(len(resp), 0)


class StudentTrainingRenderTest(StudentTrainingAssessTest):
    """
    Tests for student training step rendering.
    """
    @scenario('data/basic_scenario.xml', user_id="Plato")
    def test_no_student_training_defined(self, xblock):
        xblock.create_submission(xblock.get_student_item_dict(), self.SUBMISSION)
        resp = self.request(xblock, 'render_student_training', json.dumps({}))
        self.assertEquals("", resp.decode('utf-8'))

    @scenario('data/student_training.xml', user_id="Plato")
    def test_no_submission(self, xblock):
        resp = self.request(xblock, 'render_student_training', json.dumps({}))
        self.assertIn("Not Available", resp.decode('utf-8'))

    @scenario('data/student_training.xml')
    def test_studio_preview(self, xblock):
        resp = self.request(xblock, 'render_student_training', json.dumps({}))
        self.assertIn("Not Available", resp.decode('utf-8'))

    @scenario('data/student_training_due.xml', user_id="Plato")
    def test_past_due(self, xblock):
        xblock.create_submission(xblock.get_student_item_dict(), self.SUBMISSION)
        expected_template = "openassessmentblock/student_training/student_training_closed.html"
        expected_context = {
            'training_due': datetime.datetime(2000, 1, 1).replace(tzinfo=pytz.utc)
        }
        self._assert_path_and_context(xblock, expected_template, expected_context)

    @scenario('data/student_training.xml', user_id="Plato")
    @patch.object(StudentTrainingWorkflow, "get_or_create_workflow")
    def test_internal_error(self, xblock, mock_workflow):
        mock_workflow.side_effect = DatabaseError("Oh no.")
        xblock.create_submission(xblock.get_student_item_dict(), self.SUBMISSION)
        resp = self.request(xblock, 'render_student_training', json.dumps({}))
        self.assertIn("An unexpected error occurred.", resp.decode('utf-8'))

    @scenario('data/student_training_future.xml', user_id="Plato")
    def test_before_start(self, xblock):
        xblock.create_submission(xblock.get_student_item_dict(), self.SUBMISSION)
        expected_template = "openassessmentblock/student_training/student_training_unavailable.html"
        expected_context = {
            'training_start': datetime.datetime(3000, 1, 1).replace(tzinfo=pytz.utc)
        }
        self._assert_path_and_context(xblock, expected_template, expected_context)
