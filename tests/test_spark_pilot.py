import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_spark_pilot import split_rows
from train_spark_lora import score_predictions


class PilotTests(unittest.TestCase):
    def fixtures(self):
        rows=[dict(source_vial=i,reviewed=True,answer=json.dumps({'observed_color_sequence':['green']}),
            sha256=f'unique-{i}',baseline_color='WRONG',question='old') for i in range(1,31)]
        recipes=[dict(vial=str(i),recipe_id=str(5+(i-1)//3)) for i in range(1,31)]
        return rows,recipes

    def test_recipe_groups_stay_together(self):
        rows,recipes=self.fixtures();result=split_rows(rows,recipes)
        self.assertEqual((len(result['train']),len(result['val'])),(21,9))
        self.assertFalse({r['recipe_id'] for r in result['train']}&{r['recipe_id'] for r in result['val']})
        self.assertTrue(all('baseline_color' not in r for group in result.values() for r in group))
        self.assertEqual(rows[0]['question'],'old')

    def test_unverified_target_rejected(self):
        rows,recipes=self.fixtures();rows[0]['reviewed']=False
        with self.assertRaises(ValueError):split_rows(rows,recipes)

    def test_duplicate_media_rejected(self):
        rows,recipes=self.fixtures();rows[3]['sha256']=rows[0]['sha256']
        with self.assertRaisesRegex(ValueError,'Duplicate media'):split_rows(rows,recipes)

    def test_final_color_does_not_count_as_transition_match(self):
        result=score_predictions([dict(target=json.dumps({'observed_color_sequence':['blue','green']}),
            prediction=json.dumps({'observed_color_sequence':['green']}))])
        self.assertEqual(result['sequence_exact'],0)
        self.assertEqual(result['final_label_exact'],1)

    def test_invalid_json_and_empty_sequence_count_as_errors(self):
        target=json.dumps({'observed_color_sequence':['green']})
        result=score_predictions([dict(target=target,prediction=p) for p in ['green','{}','{"observed_color_sequence": []}']])
        self.assertEqual(result['valid_json'],0)
        self.assertEqual(result['n'],3)

    def test_case_normalization_and_fences(self):
        result=score_predictions([dict(target='{"observed_color_sequence": ["green"]}',
            prediction='```json\n{"observed_color_sequence": [" Green "]}\n```')])
        self.assertEqual(result['sequence_exact'],1)


if __name__=='__main__':unittest.main()
