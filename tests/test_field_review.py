import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_field_review import audit_row


class FieldReviewTests(unittest.TestCase):
    def row(self):
        return [7,99,1,50,None,None,50,'T100',None,None,364.634,370.634,None,7.27,None,None,'T100','Provisional']

    def test_impossible_duration_and_unverified_labels_are_not_trainable(self):
        result=audit_row(self.row())
        self.assertIn('pour_duration_exceeds_vial_window',result['flags'])
        self.assertFalse(result['training_eligible'])
        self.assertFalse(result['reviewed'])
        self.assertEqual(result['answer'],'')

    def test_agreement_does_not_promote_provisional_observation(self):
        values=self.row();values[13]=5
        result=audit_row(values)
        self.assertNotIn('pour_duration_exceeds_vial_window',result['flags'])
        self.assertFalse(result['training_eligible'])
        self.assertIsNone(result['expected']['amounts_ml']['T200'])

    def test_missing_expected_pour_and_order_conflict_are_flagged(self):
        values=self.row();values[13]=None;values[16]='T400'
        result=audit_row(values)
        self.assertIn('required_ingredient_duration_missing',result['flags'])
        self.assertIn('expected_observed_order_conflict',result['flags'])


if __name__=='__main__':unittest.main()
