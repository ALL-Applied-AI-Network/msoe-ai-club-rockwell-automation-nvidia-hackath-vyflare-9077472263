import hashlib
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from multimodal_contract import TrainingOrder,eval_subset,mixed_metrics,validate_partition
from prepare_synthetic import PALETTE,partition


class MixedTests(unittest.TestCase):
    def test_duplicate_frames_purged_and_classes_preserved(self):
        rows=[dict(frame=f,synthetic_color_name=c,sha256=f'{f}-{c}') for f in range(50) for c in PALETTE]
        rows[0]['sha256']=rows[-12]['sha256']
        a,b,info=partition(rows)
        self.assertFalse({r['frame'] for r in a}&{r['frame'] for r in b})
        self.assertFalse({r['sha256'] for r in a}&{r['sha256'] for r in b})
        self.assertEqual({r['synthetic_color_name'] for r in a},set(PALETTE))
        self.assertEqual(len(info['gap_frames']),2)

    def test_balancing_preserves_video_replay(self):
        rows=[dict(modality='image') for _ in range(100)]+[dict(modality='video')]
        order=TrainingOrder(rows,random.Random(42),True)
        chosen=[rows[order.next()]['modality'] for _ in range(80)]
        self.assertEqual(chosen.count('video'),40)
        self.assertEqual(chosen.count('image'),40)

    def test_eval_subset_keeps_real_regression(self):
        rows=[dict(id=str(i),target_kind='render_control') for i in range(120)]+[dict(id='real',target_kind='observed_color')]
        selected=eval_subset(rows,13)
        self.assertEqual(selected[0]['id'],'real')
        self.assertEqual(len(selected),13)

    def test_metrics_do_not_conflate_render_class_and_observation(self):
        result=mixed_metrics([
            dict(target_kind='render_control',target='{"render_color_class":"navy"}',prediction='{"render_color_class":"blue"}'),
            dict(target_kind='observed_color',target='{"observed_color_sequence":["blue","green"]}',prediction='{"observed_color_sequence":["green"]}')])
        self.assertEqual(result['by_target_kind']['render_control']['render_control_exact'],0)
        self.assertEqual(result['by_target_kind']['observed_color']['sequence_exact'],0)
        self.assertEqual(result['by_target_kind']['observed_color']['final_label_exact'],1)

    def test_renderer_identity_cannot_be_used_as_real_label(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def row(name,domain):
                (root/name).write_bytes(name.encode())
                return dict(id=name,media=name,sha256=hashlib.sha256(name.encode()).hexdigest(),
                            split_group=name,target_kind='render_control',domain=domain,modality='image',
                            answer=json.dumps({'render_color_class':'red'}))
            a=row('a.png','real');b=row('b.png','synthetic')
            with self.assertRaisesRegex(ValueError,'synthetic images'):validate_partition([a],[b],root,True)


if __name__=='__main__':unittest.main()
