import copy
import json
import unittest
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from camera_control.app import Runtime,create_app
from camera_control.calibration import build_calibration
from camera_control.camera_test import test_config,main
from camera_control.sources import Frame,clock


def settings(**overrides):
    return dict(camera='cam0',lane='test_lane',roi=[[.05,.2],[.95,.8]],a=[.3,.5],b=[.7,.5],
                mode='time',time_threshold_s=2.,led_interval_s=.25,threshold=25,min_area=10,max_match_distance=30,**overrides)


class CalibrationTests(unittest.TestCase):
    def config(self):return test_config(size=(200,120))
    def runtime(self):
        r=Runtime(self.config(),mode='usb')
        r.sources['cam0'].publish(np.zeros((120,200),dtype=np.uint8),clock(),'test')
        return r

    def test_one_camera_launcher_does_not_open_in_check_mode(self):
        import contextlib,io
        with patch('camera_control.app.USBSource.start',side_effect=AssertionError('opened')),contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(['--check']),0)
        self.assertIn('no camera',out.getvalue())
        self.assertFalse(test_config()['outputs_enabled'])

    def test_screen_coordinates_scale_to_actual_image_and_direction(self):
        config=self.config();proposed=build_calibration(config,settings(),(200,120))
        lane=proposed['vision']['lanes'][0]
        self.assertAlmostEqual(lane['gate_a'][0][0],59.7)
        self.assertAlmostEqual(lane['gate_b'][0][0],139.3)
        self.assertGreater(lane['direction'][0],0)
        self.assertFalse(config['vision']['lanes'])
        vertical=settings();vertical['a']=[.5,.3];vertical['b']=[.5,.7]
        lane=build_calibration(config,vertical,(200,120))['vision']['lanes'][0]
        self.assertAlmostEqual(lane['gate_a'][0][1],35.7)
        self.assertAlmostEqual(lane['gate_a'][1][1],35.7)

    def test_invalid_geometry_or_parameters_rejected_without_mutation(self):
        for key,value in [('roi',[[.1,.1],[.11,.11]]),('a',[2,.5]),('a',[True,.5]),('b',[.3,.5]),
                          ('b',[.97,.5]),('threshold',True),('min_area',0),('led_interval_s',float('nan'))]:
            config=self.config();v=settings();v[key]=value
            with self.assertRaises(ValueError,msg=key):build_calibration(config,v,(200,120))
            self.assertFalse(config['vision']['lanes'])

    def test_missing_or_stale_image_cannot_calibrate(self):
        r=Runtime(self.config(),mode='usb')
        with self.assertRaises(ValueError):r.apply_calibration(settings())
        r.sources['cam0'].publish(np.zeros((120,200),np.uint8),clock()-10,'test')
        with self.assertRaises(ValueError):r.apply_calibration(settings())

    def test_calibration_requires_empty_background_after_apply(self):
        r=self.runtime();r.apply_calibration(settings())
        self.assertFalse(r.backgrounds)
        r.capture_background('cam0');self.assertTrue(r.status()['cameras'][0]['calibrated'])
        r.apply_calibration(settings());self.assertFalse(r.status()['cameras'][0]['calibrated'])

    def test_waiting_or_locked_route_cannot_change_calibration(self):
        for locked in (False,True):
            r=self.runtime();r.apply_calibration(settings());r.capture_background('cam0')
            t=clock()-2;r.manager.ingest(dict(lane='test_lane',gate='A',track_id=1,timestamp=t))
            if locked:r.manager.ingest(dict(lane='test_lane',gate='B',track_id=1,timestamp=t+1))
            before=copy.deepcopy(r.config)
            with self.assertRaises(ValueError):r.apply_calibration(settings())
            self.assertEqual(r.config,before);self.assertTrue(r.backgrounds)

    def test_mock_position_and_history_survive_release_and_setting_change(self):
        r=self.runtime();r.apply_calibration(settings());t=clock()-2
        r.manager.ingest(dict(lane='test_lane',gate='A',track_id=1,timestamp=t))
        r.manager.ingest(dict(lane='test_lane',gate='B',track_id=1,timestamp=t+1))
        r.release('test_lane',True);v=settings();v['mode']='led';r.apply_calibration(v)
        status=r.status()['routes'];self.assertEqual(status['lanes'][0]['last_requested_route'],'straight')
        self.assertEqual(len(status['requests']),1);self.assertFalse(r.status()['outputs_enabled'])

    def test_real_source_frame_path_drives_only_mock_output_after_b_for_both_modes(self):
        for mode,expected in [('time','straight'),('led','curve')]:
            r=self.runtime();v=settings();v['mode']=mode;r.apply_calibration(v);r.capture_background('cam0')
            base=clock()-5
            for n,x in enumerate(range(20,166,5)):
                image=np.zeros((120,200),np.uint8);image[55:66,x-6:x+7]=200
                r.process_frame('cam0',Frame(image,base+n*.025,n,'test_usb'))
                if x<140:self.assertEqual(r.manager.status(clock())['requests'],[])
            result=r.status();requests=result['routes']['requests']
            self.assertEqual(len(requests),1);self.assertEqual(requests[0]['route'],expected)
            self.assertTrue(requests[0]['simulated']);self.assertFalse(requests[0]['hardware_outputs_enabled'])
            self.assertTrue(result['tracks'][0]['bbox']);self.assertGreater(result['tracks'][0]['area'],10)

    def test_http_apply_snapshot_and_export_without_starting_camera_or_enabling_outputs(self):
        app=create_app(self.config(),mode='usb');r=app.state.runtime
        r.sources['cam0'].publish(np.zeros((120,200),np.uint8),clock(),'test')
        client=TestClient(app) # No lifespan context: no source thread or physical device.
        self.assertEqual(client.get('/api/snapshot/cam0.jpg').status_code,200)
        self.assertEqual(client.post('/api/calibration',json=settings()).status_code,200)
        self.assertEqual(client.post('/api/calibration',json={**settings(),'outputs_enabled':True}).status_code,422)
        self.assertEqual(client.post('/api/calibration',json={**settings(),'a':[True,.5]}).status_code,422)
        exported=client.get('/api/config/download')
        self.assertIn('attachment',exported.headers['content-disposition'])
        self.assertEqual(len(exported.json()['vision']['lanes']),1);self.assertFalse(exported.json()['outputs_enabled'])
        self.assertEqual(client.get('/api/status').json()['cameras'][0]['frame_size'],[200,120])


if __name__=='__main__':unittest.main()
