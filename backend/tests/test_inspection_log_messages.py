from copy import deepcopy
import unittest

from recipes.inspection_log import outcome, clarify_saved_outcomes


class ClearOutcomeTests(unittest.TestCase):
    def assessment(self):
        return {'action':'UNRESOLVED','recipe_id':None,
            'hold_reasons':['ARRIVAL_LEFT_CENSORED','AVAILABLE_DEMO_CHECKS_NOT_PASSED'],
            'timing':{'possible_recipe_ids':[7],'status':'BOUNDARY_UNCERTAIN'},
            'color':{'status':'CONSISTENT'},'observation':{'label':'Video 1 · Vial 1'}}

    def test_possible_recipe_does_not_become_an_assigned_identity(self):
        a=self.assessment();before=deepcopy(a)
        self.assertEqual(outcome(a),('Unresolved — Possible Recipe 7',
            'Final color resembles Recipe 7, but dispense timing remains at the matching boundary. '
            'The vial was also present before recording began, so its arrival was not observed. '
            'No recipe ID was assigned or created.'))
        self.assertEqual(a,before)

    def test_color_conflict_is_not_described_as_a_color_match(self):
        a=self.assessment();a['color']['status']='CONFLICTING'
        title,detail=outcome(a)
        self.assertIn('Possible Recipe 7',title)
        self.assertIn('Final color conflicts',detail)
        self.assertNotIn('Final color resembles',detail)

    def test_missing_comparison_does_not_invent_a_possible_recipe(self):
        a=self.assessment();a['timing']={'possible_recipe_ids':[],'status':'NO_COMPATIBLE_REFERENCE'}
        a['color']['status']='NOT_EVALUATED'
        title,detail=outcome(a)
        self.assertEqual(title,'Unresolved')
        self.assertIn('No final-color recipe comparison was available.',detail)
        self.assertNotIn('matching boundary',detail)

    def test_saved_presentation_keeps_event_identity_time_and_original_record(self):
        old={'id':'saved-id','at':30,'kind':'recipe','vial':'Video 1 · Vial 1',
            'title':'Unresolved','detail':'Timing candidates: 7. Flags: arrival left censored'}
        before=deepcopy(old)
        rendered=clarify_saved_outcomes([old],[self.assessment()])[0]
        self.assertEqual(rendered['id'],old['id']);self.assertEqual(rendered['at'],30)
        self.assertEqual(rendered['title'],'Unresolved — Possible Recipe 7')
        self.assertEqual(old,before)

    def test_later_membership_events_are_not_rewritten_from_the_baseline(self):
        later={'kind':'recipe','vial':'Video 1 · Vial 1','title':'Observed Recipe 100 · Unverified · Color Review','at':90}
        self.assertEqual(clarify_saved_outcomes([later],[self.assessment()]),[later])
