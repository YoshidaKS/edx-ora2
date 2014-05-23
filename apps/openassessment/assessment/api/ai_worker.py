"""
Public interface for AI training and grading, used by workers.
"""
import logging
from django.utils.timezone import now
from django.db import DatabaseError
from openassessment.assessment.models import (
    AITrainingWorkflow, AIGradingWorkflow, AIClassifierSet,
    ClassifierUploadError, ClassifierSerializeError,
    IncompleteClassifierSet, NoTrainingExamples
)
from openassessment.assessment.errors import (
    AITrainingRequestError, AITrainingInternalError,
    AIGradingRequestError, AIGradingInternalError
)


logger = logging.getLogger(__name__)


def get_grading_task_params(grading_workflow_uuid):
    """
    Retrieve the classifier set and algorithm ID
    associated with a particular grading workflow.

    Args:
        grading_workflow_uuid (str): The UUID of the grading workflow.

    Returns:
        dict with keys:
            * essay_text (unicode): The text of the essay submission.
            * classifier_set (dict): Maps criterion names to serialized classifiers.
            * algorithm_id (unicode): ID of the algorithm used to perform training.

    Raises:
        AIGradingRequestError
        AIGradingInternalError

    """
    try:
        workflow = AIGradingWorkflow.objects.get(uuid=grading_workflow_uuid)
    except AIGradingWorkflow.DoesNotExist:
        msg = (
            u"Could not retrieve the AI grading workflow with uuid {}"
        ).format(grading_workflow_uuid)
        raise AIGradingRequestError(msg)
    except DatabaseError as ex:
        msg = (
            u"An unexpected error occurred while retrieving the "
            u"AI grading workflow with uuid {uuid}: {ex}"
        ).format(uuid=grading_workflow_uuid, ex=ex)
        logger.exception(msg)
        raise AIGradingInternalError(msg)

    classifier_set = workflow.classifier_set
    # Tasks shouldn't be scheduled until a classifier set is
    # available, so this is a serious internal error.
    if classifier_set is None:
        msg = (
            u"AI grading workflow with UUID {} has no classifier set"
        ).format(grading_workflow_uuid)
        logger.exception(msg)
        raise AIGradingInternalError(msg)

    try:
        return {
            'essay_text': workflow.essay_text,
            'classifier_set': classifier_set.classifiers_dict,
            'algorithm_id': workflow.algorithm_id,
        }
    except (ValueError, IOError, DatabaseError) as ex:
        msg = (
            u"An unexpected error occurred while retrieving "
            u"classifiers for the grading workflow with UUID {uuid}: {ex}"
        ).format(uuid=grading_workflow_uuid, ex=ex)
        logger.exception(msg)
        raise AIGradingInternalError(msg)


def create_assessment(grading_workflow_uuid, criterion_scores):
    """
    Create an AI assessment (complete the AI grading task).

    Args:
        grading_workflow_uuid (str): The UUID of the grading workflow.
        criterion_scores (dict): Dictionary mapping criteria names to integer scores.

    Returns:
        None

    Raises:
        AIGradingRequestError
        AIGradingInternalError

    """
    try:
        workflow = AIGradingWorkflow.objects.get(uuid=grading_workflow_uuid)
    except AIGradingWorkflow.DoesNotExist:
        msg = (
            u"Could not retrieve the AI grading workflow with uuid {}"
        ).format(grading_workflow_uuid)
        raise AIGradingRequestError(msg)
    except DatabaseError as ex:
        msg = (
            u"An unexpected error occurred while retrieving the "
            u"AI grading workflow with uuid {uuid}: {ex}"
        ).format(uuid=grading_workflow_uuid, ex=ex)
        logger.exception(msg)
        raise AIGradingInternalError(msg)

    # Optimization: if the workflow has already been marked complete
    # (perhaps the task was picked up by multiple workers),
    # then we don't need to do anything.
    # Otherwise, create the assessment mark the workflow complete.
    try:
        if not workflow.is_complete:
            workflow.complete(criterion_scores)
    except DatabaseError as ex:
        msg = (
            u"An unexpected error occurred while creating the assessment "
            u"for AI grading workflow with uuid {uuid}: {ex}"
        ).format(uuid=grading_workflow_uuid, ex=ex)
        logger.exception(msg)
        raise AIGradingInternalError(msg)


def get_training_task_params(training_workflow_uuid):
    """
    Retrieve the training examples and algorithm ID
    associated with a training task.

    Args:
        training_workflow_uuid (str): The UUID of the training workflow.

    Returns:
        dict with keys:
            * training_examples (list of dict): The examples used to train the classifiers.
            * algorithm_id (unicode): The ID of the algorithm to use for training.

    Raises:
        AITrainingRequestError
        AITrainingInternalError

    Example usage:
        >>> params = get_training_task_params('abcd1234')
        >>> params['algorithm_id']
        u'ease'
        >>> params['training_examples']
        [
            {
                "text": u"Example answer number one",
                "scores": {
                    "vocabulary": 1,
                    "grammar": 2
                }
            },
            {
                "text": u"Example answer number two",
                "scores": {
                    "vocabulary": 3,
                    "grammar": 1
                }
            }
        ]

    """
    try:
        workflow = AITrainingWorkflow.objects.get(uuid=training_workflow_uuid)
        returned_examples = []

        for example in workflow.training_examples.all():
            answer = example.answer
            if isinstance(answer, dict):
                text = answer.get('answer', '')
            else:
                text = answer

            scores = {
                option.criterion.name: option.points
                for option in example.options_selected.all()
            }

            returned_examples.append({
                'text': text,
                'scores': scores
            })

        return {
            'training_examples': returned_examples,
            'algorithm_id': workflow.algorithm_id
        }
    except AITrainingWorkflow.DoesNotExist:
        msg = (
            u"Could not retrieve AI training workflow with UUID {}"
        ).format(training_workflow_uuid)
        raise AITrainingRequestError(msg)
    except DatabaseError:
        msg = (
            u"An unexpected error occurred while retrieving "
            u"training examples for the AI training workflow with UUID {}"
        ).format(training_workflow_uuid)
        logger.exception(msg)
        raise AITrainingInternalError(msg)


def create_classifiers(training_workflow_uuid, classifier_set):
    """
    Upload trained classifiers and mark the workflow complete.

    If grading tasks were submitted before any classifiers were trained,
    this call will automatically reschedule those tasks.

    Args:
        training_workflow_uuid (str): The UUID of the training workflow.
        classifier_set (dict): Mapping of criteria names to serialized classifiers.

    Returns:
        None

    Raises:
        AITrainingRequestError
        AITrainingInternalError

    """
    try:
        workflow = AITrainingWorkflow.objects.get(uuid=training_workflow_uuid)

        # If the task is executed multiple times, the classifier set may already
        # have been created.  If so, log a warning then return immediately.
        if workflow.is_complete:
            msg = u"AI training workflow with UUID {} already has trained classifiers."
            logger.warning(msg)
        else:
            workflow.complete(classifier_set)
    except AITrainingWorkflow.DoesNotExist:
        msg = (
            u"Could not retrieve AI training workflow with UUID {}"
        ).format(training_workflow_uuid)
        raise AITrainingRequestError(msg)
    except NoTrainingExamples as ex:
        logger.exception(ex)
        raise AITrainingInternalError(ex)
    except IncompleteClassifierSet as ex:
        msg = (
            u"An error occurred while creating the classifier set "
            u"for the training workflow with UUID {uuid}: {ex}"
        ).format(uuid=training_workflow_uuid, ex=ex)
        raise AITrainingRequestError(msg)
    except (ClassifierSerializeError, ClassifierUploadError, DatabaseError) as ex:
        msg = (
            u"An unexpected error occurred while creating the classifier "
            u"set for training workflow UUID {uuid}: {ex}"
        ).format(uuid=training_workflow_uuid, ex=ex)
        logger.exception(msg)
        raise AITrainingInternalError(msg)
    except DatabaseError:
        msg = (
            u"An unexpected error occurred while creating the classifier set "
            u"for the AI training workflow with UUID {}"
        ).format(training_workflow_uuid)
        logger.exception(msg)
        raise AITrainingInternalError(msg)