import sys
import types
import unittest
from unittest.mock import patch

import numpy as np

from camera_control.sources import DemoSource, LatestSource, PiSource, clock


class SourceTests(unittest.TestCase):
    def test_latest_frame_is_bounded_and_copied(self):
        source=LatestSource({'id':'cam0'})
        image=np.zeros((4,4),np.uint8)
        source.publish(image,1,'test');first=source.latest()
        image[:]=255
        self.assertEqual(int(first.image[0,0]),0)
        source.publish(image,2,'test')
        self.assertEqual(source.latest().sequence,2)
        self.assertEqual(source.frames,2)
        self.assertEqual(int(source.latest().image[0,0]),255)

    def test_demo_has_empty_reference_and_keeps_stop(self):
        source=DemoSource({'id':'cam0'})
        self.assertTrue(np.array_equal(source.image_at(4.5),source.image_at(5.5)))
        self.assertFalse(np.array_equal(source.image_at(5.5),source.empty_image()))

    def test_pi_chooses_full_field_mode_without_upscaling_and_releases_request(self):
        source=PiSource({'id':'cam0','index':0,'main_size':[1920,1080],
                         'processing_size':[1280,720],'fps':15})
        marks=[]
        class Request:
            def get_metadata(self):return {'SensorTimestamp':round(clock()*1e9)}
            def make_array(self,stream):
                self.array=np.full((1080,1280),80,np.uint8)
                return self.array
            def release(self):
                marks.append('release');self.array[:]=0
        class Camera:
            sensor_modes=[{'size':(1920,1080),'crop_limits':(100,100,3840,2160),'fps':60,'bit_depth':10},
                          {'size':(1536,864),'crop_limits':(0,0,4608,2592),'fps':120,'bit_depth':10},
                          {'size':(2304,1296),'crop_limits':(0,0,4608,2592),'fps':56,'bit_depth':10}]
            def __init__(self,index):self.index=index
            def create_video_configuration(self,**kwargs):self.cfg=kwargs;return kwargs
            def configure(self,c):pass
            def start(self):marks.append('start')
            def capture_request(self):return Request()
            def stop(self):marks.append('stop')
            def close(self):marks.append('close')
        publish=source.publish
        def once(*args):publish(*args);source._stop.set()
        source.publish=once
        with patch.dict(sys.modules,{'picamera2':types.SimpleNamespace(Picamera2=Camera)}):source._run()
        self.assertIsNone(source.error)
        self.assertEqual(source.camera.cfg['sensor']['output_size'],(2304,1296))
        self.assertEqual(source.latest().image.shape,(720,1280))
        self.assertEqual(int(source.latest().image[0,0]),80)
        self.assertEqual(marks,['start','release','stop','close'])


if __name__=='__main__':unittest.main()
