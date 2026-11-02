"""Screen-click calibration for one straight test section, with no hardware I/O."""
from __future__ import annotations
import copy
import math


def build_calibration(config, value, size):
    camera, ident = value['camera'], value['lane']
    if camera not in {c['id'] for c in config['cameras']}:
        raise ValueError('不明なカメラです')
    if ident not in {l['id'] for l in config['routes']['lanes']}:
        raise ValueError('不明な線区です')
    width, height = size
    if width < 32 or height < 32:
        raise ValueError('画像サイズが小さすぎます')

    def point(p):
        if not isinstance(p, list) or len(p) != 2:
            raise ValueError('座標は2個で指定してください')
        if any(isinstance(n, bool) or not isinstance(n, (float, int)) or not math.isfinite(n) or not 0 <= n <= 1 for n in p):
            raise ValueError('画面内の座標を指定してください')
        return [p[0]*(width-1), p[1]*(height-1)]

    roi = value['roi']
    if not isinstance(roi, list) or len(roi) != 2:
        raise ValueError('検出範囲の対角2点を指定してください')
    p, q = map(point, roi)
    x0, x1 = sorted((p[0], q[0])); y0, y1 = sorted((p[1], q[1]))
    if x1-x0 < 12 or y1-y0 < 12:
        raise ValueError('検出範囲は幅・高さとも12画素以上にしてください')
    a, b = point(value['a']), point(value['b'])
    if any(not x0 < v[0] < x1 or not y0 < v[1] < y1 for v in (a, b)):
        raise ValueError('A・Bは検出範囲の内側をクリックしてください')
    dx, dy = b[0]-a[0], b[1]-a[1]
    if math.hypot(dx, dy) < 10:
        raise ValueError('A・Bを10画素以上離してください')
    # Intersect a perpendicular infinite line through A/B with the rectangle.
    def gate(center):
        vx, vy = -dy, dx
        low, high = -math.inf, math.inf
        for origin, velocity, minimum, maximum in ((center[0],vx,x0,x1),(center[1],vy,y0,y1)):
            if abs(velocity) < 1e-12:
                continue
            t0, t1 = sorted(((minimum-origin)/velocity, (maximum-origin)/velocity))
            low, high = max(low,t0), min(high,t1)
        return [[center[0]+t*vx,center[1]+t*vy] for t in (low,high)]
    mode = value['mode']
    if mode not in ('time','led'):
        raise ValueError('時間差方式またはLED方式を選んでください')
    for key in ('time_threshold_s','led_interval_s'):
        n=value[key]
        if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) or not .1 <= n <= 60:
            raise ValueError('時間は0.1〜60秒で指定してください')
    for key, minimum, maximum in [('threshold',1,255),('min_area',1,width*height),('max_match_distance',1,1000)]:
        n=value[key]
        if type(n) is not int or not minimum <= n <= maximum:
            raise ValueError(f'{key}は{minimum}〜{maximum}の整数で指定してください')
    result = copy.deepcopy(config)
    lane = dict(id=ident,camera=camera,polygon=[[x0,y0],[x1,y0],[x1,y1],[x0,y1]],
                gate_a=gate(a),gate_b=gate(b),direction=[dx,dy])
    result['vision']['lanes']=[l for l in result['vision'].get('lanes',[]) if l['id']!=ident]+[lane]
    for key in ('threshold','min_area','max_match_distance'):
        result['vision'][key]=value[key]
    for route in result['routes']['lanes']:
        if route['id']==ident:
            for key in ('mode','time_threshold_s','led_interval_s'): route[key]=value[key]
    result['outputs_enabled']=False
    return result
