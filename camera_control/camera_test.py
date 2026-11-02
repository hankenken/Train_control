"""One-camera PC test: real USB images, screen-only simulated control outputs."""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def test_config(device=0, backend='dshow', size=(640,480), fps=15, fourcc='MJPG'):
    if type(device) is not int or device<0:raise ValueError('カメラ番号は0以上の整数です')
    if backend not in ('dshow','msmf','auto'):raise ValueError('不明なbackendです')
    if len(size)!=2 or any(type(n) is not int or n<32 or n>4096 for n in size):raise ValueError('画像サイズは32〜4096の整数2個です')
    if type(fps) is not int or not 1<=fps<=60:raise ValueError('fpsは1〜60の整数です')
    if not isinstance(fourcc,str) or len(fourcc)!=4 or not fourcc.isascii():raise ValueError('fourccはASCII4文字です')
    return {'schema_version':1,'outputs_enabled':False,
            'layout_note':'USBカメラ1台・直線1区間の認識と模擬制御の検証。機器への出力はありません。',
            'routes':{'lanes':[{'id':'test_lane','mode':'time','time_threshold_s':2,'led_interval_s':2}]},
            'vision':{'lanes':[],'threshold':25,'min_area':30,'max_match_distance':80,'lost_timeout':1.,'max_tracks':4,'morph_kernel':3},
            'cameras':[{'id':'cam0','name':'検証用USBカメラ','device':device,'backend':backend,'fps':fps,
                        'capture_size':list(size),'processing_size':list(size),'fourcc':fourcc,'properties':{}}],
            'preview_fps':4,'stale_frame_s':.75}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device',type=int,default=0,help='USB camera index; try another index if the wrong camera appears')
    parser.add_argument('--backend',choices=('dshow','msmf','auto'),default='dshow')
    parser.add_argument('--capture-size',nargs=2,type=int,default=(640,480),metavar=('WIDTH','HEIGHT'))
    parser.add_argument('--fps',type=int,default=15)
    parser.add_argument('--fourcc',default='MJPG')
    parser.add_argument('--config',help='Optional previously downloaded camera-test.local.json')
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--check',action='store_true',help='Print configuration; never open a camera, COM port, or server')
    args=parser.parse_args(argv)
    from .app import create_app,read_config
    try:
        config=read_config(Path(args.config)) if args.config else test_config(args.device,args.backend,args.capture_size,args.fps,args.fourcc)
        if not 1024<=args.port<=65535:raise ValueError('ポートは1024〜65535を指定してください')
        if args.check:
            print(json.dumps(config,ensure_ascii=False,indent=2))
            print('CHECK ONLY: no camera, COM port, driver or server was opened.')
            return 0
        app=create_app(config,mode='usb')
    except (ValueError,KeyError,OSError) as exc:parser.error(str(exc))
    print(f'Open http://127.0.0.1:{args.port} in Chrome or Edge. Stop with Ctrl+C.')
    print('USB CAMERA TEST: all control outputs are simulated on screen. No serial/GPIO output.')
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=args.port)
    return 0


if __name__=='__main__':raise SystemExit(main())
