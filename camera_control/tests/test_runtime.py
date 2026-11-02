import copy
import json
from pathlib import Path
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from camera_control.app import ROOT, Runtime, create_app, read_config
from camera_control.sources import DemoSource, Frame, clock


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.config = read_config(ROOT/'config/demo.json')

    def test_four_synthetic_trains_generate_four_decisions_only_after_b(self):
        runtime = Runtime(self.config)
        base = clock()-20
        for tick in range(150):
            t = tick/15
            for camera, source in runtime.sources.items():
                runtime.process_frame(camera, Frame(source.image_at(t), base+t, tick+1, 'test'))
            if t < 8:
                self.assertEqual(runtime.manager.status(clock())['requests'], [])
        requests = runtime.manager.status(clock())['requests']
        self.assertEqual(len(requests), 4)
        self.assertEqual({r['lane'] for r in requests}, {r['id'] for r in self.config['routes']['lanes']})
        self.assertTrue(all(r['simulated'] for r in requests))
        self.assertFalse(runtime.status()['outputs_enabled'])
        self.assertEqual(runtime.release('upper_outer', False)['accepted'], False)
        self.assertTrue(runtime.release('upper_outer', True)['accepted'])
        self.assertEqual(len(runtime.manager.status(clock())['requests']), 4)

    def test_pause_does_not_join_positions_across_unprocessed_interval(self):
        runtime = Runtime(self.config)
        base = clock()-20
        source = runtime.sources['cam0']
        for n,t in enumerate([1.5,2,2.5,3,3.5]):
            runtime.process_frame('cam0', Frame(source.image_at(t), base+t, n, 'test'))
        self.assertEqual(runtime.manager.status(clock())['lanes'][0]['state'], 'waiting')
        runtime.pause(True)
        runtime.pause(False)
        runtime.process_frame('cam0', Frame(source.image_at(9), base+9, 6, 'test'))
        self.assertEqual(runtime.manager.status(clock())['requests'], [])
        self.assertEqual(runtime.manager.status(clock())['lanes'][0]['state'], 'uncertain')

    def test_pi_config_starts_without_guessed_geometry_or_background(self):
        config = read_config(ROOT/'config/pi5.example.json')
        runtime = Runtime(config, mode='pi')
        self.assertFalse(runtime.backgrounds)
        self.assertFalse(runtime.vision_lanes)
        self.assertEqual(len(runtime.status()['routes']['lanes']), 4)
        self.assertTrue(runtime.status()['warnings'])
        self.assertFalse(runtime.status()['outputs_enabled'])

    def test_http_dashboard_status_and_rejected_release(self):
        with TestClient(create_app(self.config)) as client:
            self.assertEqual(client.get('/').status_code, 200)
            status = client.get('/api/status').json()
            self.assertFalse(status['outputs_enabled'])
            self.assertEqual(len(status['cameras']), 2)
            self.assertEqual(client.post('/api/release/upper_outer', json={'confirm_clear':False}).status_code, 409)
            self.assertEqual(client.post('/api/pause',json={'paused':True}).json()['paused'],True)
            self.assertEqual(client.post('/api/pause',json={'paused':'false'}).status_code,422)
            self.assertEqual(client.get('/api/preview/no-such-camera.mjpg').status_code,404)
            self.assertEqual(client.post('/api/background/no-such-camera').status_code,404)

    def test_logs_record_only_simulated_requests(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d)/'events.jsonl'
            runtime = Runtime(self.config, log_path=log)
            for e in [{'lane':'upper_outer','gate':'A','track_id':9,'timestamp':clock()-3},
                      {'lane':'upper_outer','gate':'B','track_id':9,'timestamp':clock()-1}]:
                result=runtime.manager.ingest(e)
                if result['decision']:
                    runtime.record({'kind':'decision',**result['decision']})
            rows=[json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(len(rows),1)
            self.assertTrue(rows[0]['simulated'])

    def test_lattepanda_config_uses_two_usb_sources_without_opening_devices(self):
        config = read_config(ROOT/'config/lattepanda.example.json')
        runtime = Runtime(config, mode='usb')
        self.assertEqual([s.config['device'] for s in runtime.sources.values()], [0,1])
        self.assertTrue(all(s.latest() is None for s in runtime.sources.values()))
        self.assertFalse(runtime.status()['outputs_enabled'])
        self.assertTrue(any('USB' in w for w in runtime.status()['warnings']))
        self.assertFalse(runtime.vision_lanes)

    def test_duplicate_usb_device_or_invalid_dimensions_are_rejected(self):
        config = read_config(ROOT/'config/lattepanda.example.json')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.json'
            for change in ['duplicate','size']:
                bad=copy.deepcopy(config)
                if change=='duplicate':bad['cameras'][1]['device']=0
                else:bad['cameras'][0]['capture_size']=[0,1080]
                p.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):read_config(p)

    def test_config_cannot_enable_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'bad.json'
            config=copy.deepcopy(self.config);config['outputs_enabled']=True
            path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):read_config(path)


if __name__=='__main__':unittest.main()
