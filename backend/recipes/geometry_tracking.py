"""Experimental fixed-station pixel geometry. No recipes, labels or model weights.

Coordinates are normalized to the unmodified 640x480 camera image. The active filling station
lane is searched; this is not a detector for arbitrary cameras or containers.
"""
import math
import hashlib
from pathlib import Path
import numpy as np

VERSION = 'fixed-station-geometry/1'
SLOTS = (("Filling Position", 250, 385, 308),)
IMPLEMENTATION_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
CONFIG = {'version': VERSION, 'implementation_sha256': IMPLEMENTATION_SHA, 'width': 640, 'height': 480, 'maximum_gap_seconds': .4,
          'confirm_frames': 2, 'motion_threshold': 2., 'surface_minimum_contrast': 18.,
          'scope': 'Active filling position in the fixed 640 × 480 vial-fill station; experimental visual evidence only'}


def _peaks(values, lo, hi, count=8):
    candidates=sorted(range(lo,hi),key=lambda x:float(values[x]),reverse=True)
    chosen=[]
    for x in candidates:
        if all(abs(x-y)>3 for y in chosen):chosen.append(x)
        if len(chosen)==count:break
    return chosen


def detect_vials(pixels):
    if pixels.shape!=(480,640,3):raise ValueError('Tracking requires the original 640 × 480 RGB station view; frames are not resized')
    a=pixels.astype(np.float32);gray=a.mean(axis=2)
    gradient=np.abs(gray[:,2:]-gray[:,:-2]); scores=np.median(gradient[285:375],axis=0)
    detections=[]
    for label,lo,hi,anchor in SLOTS:
        # Require two sustained glass/body edges around the station center.
        lefts=_peaks(scores,lo,anchor-8);rights=_peaks(scores,anchor+8,min(hi-2,anchor+44))
        pairs=[]
        for li in lefts:
            for ri in rights:
                width=ri-li
                if not 38<=width<=66:continue
                support=min(float(np.mean(gradient[285:375,li]>4)),float(np.mean(gradient[285:375,ri]>4)))
                strength=min(float(scores[li]),float(scores[ri]))
                score=strength*support-abs((li+ri)/2-anchor)*.16
                if strength>=4 and support>=.4:pairs.append((score,li+1,ri+1,support,strength))
        if not pairs:continue
        _,left,right,support,strength=max(pairs)
        # The upper rim and curved bottom are located from image edges, rather
        # than extending the liquid-colored interior to a fixed annotation box.
        x0=max(lo,left-8);x1=min(hi,right+8);w=x1-x0
        dy=np.abs(gray[2:]-gray[:-2])
        side_columns=list(range(x0,x0+max(3,w//4)))+list(range(x1-max(3,w//4),x1))
        rim=np.mean(dy[64:120,side_columns],axis=1)
        top=int(np.argmax(rim-np.abs(np.arange(64,120)-76)*.08))+65
        rim_strength=float(rim[top-65])
        if rim_strength<2.5:continue
        base=np.mean(dy[390:430,left+4:right-4],axis=1)
        bottom=int(np.argmax(base))+391
        if bottom-top<240:continue
        box={'x':x0/640,'y':top/480,'width':w/640,'height':(bottom-top)/480}
        surface,reason=detect_surface(a,left+5,right-5,top,bottom)
        detections.append({'position':label,'box':box,'edge_support':round(support,3),
            'edge_contrast':round(strength,2),'rim_contrast':round(rim_strength,2),
            'surface':surface,'surface_reason':reason,
            'holder_signature':gray[200:275,lo:hi].copy()})
    return detections


def detect_surface(a,left,right,top,bottom):
    """Only report a coherent, colored liquid/air boundary in visible glass.

    Label/holder bands are excluded. A hidden boundary, clear liquid, meniscus
    glare or a filled tube without a visible top produces no asserted level.
    """
    if right-left<18:return None,'INSUFFICIENT_VISIBLE_WIDTH'
    candidates=[]
    for lower,upper in ((max(top+16,95),155),(280,min(bottom-20,390))):
        if upper-lower<16:continue
        for y in range(lower+6,upper-10):
            above=np.median(a[y-6:y-2,left:right],axis=0)
            below=np.median(a[y+3:y+9,left:right],axis=0)
            delta=np.linalg.norm(below-above,axis=1)
            # A genuine boundary spans most of the inner vial width, and the
            # liquid below is chromatic and differs from the nearby background.
            chroma=below.max(axis=1)-below.min(axis=1)
            above_chroma=above.max(axis=1)-above.min(axis=1)
            valid=(delta>=18)&(chroma>=24)&(above_chroma<22)&((chroma-above_chroma)>=16)
            if np.mean(valid)<.65:continue
            # Reject a thin bright/dark stripe: the appearance persists below.
            deep=np.median(a[y+9:min(y+18,bottom-8),left:right],axis=(0,1))
            if np.linalg.norm(deep-np.median(below,axis=0))>24:continue
            candidates.append((float(np.median(delta))*float(np.mean(valid)),y,float(np.mean(valid))))
    if not candidates:return None,'OCCLUDED_EMPTY_CLEAR_OR_LOW_CONTRAST'
    candidates.sort(reverse=True)
    score,y,support=candidates[0]
    # Multiple distinct boundaries are ambiguous; never pick a holder edge.
    if any(abs(other_y-y)>12 and other_score>score*.8 for other_score,other_y,_ in candidates[1:]):
        return None,'MULTIPLE_SURFACE_CANDIDATES'
    return {'x1':left/640,'x2':right/640,'y1':y/480,'y2':y/480,
            'support':round(support,3),'contrast':round(score,2)},'VISIBLE_BOUNDARY'


class GeometryTracker:
    def __init__(self):
        self.previous=None;self.last_time=None;self.slots={};self.counter=0

    def step(self,pixels,seconds):
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<0:
            raise ValueError('Capture time must be finite and nonnegative')
        if self.last_time is not None and seconds<=self.last_time:raise ValueError('Capture times must increase; reset the session after seeking')
        gap=self.last_time is not None and seconds-self.last_time>CONFIG['maximum_gap_seconds']
        if gap:self.slots={}
        found=detect_vials(pixels);output=[];present=set()
        for d in found:
            name=d['position'];present.add(name);signature=d.pop('holder_signature')
            old=self.slots.get(name);motion=None
            if old is not None:
                change=np.abs(signature-old['signature'])
                motion=min(float(np.mean(change[:,:25])),float(np.mean(change[:,-25:])))
            moving=motion is not None and motion>=CONFIG['motion_threshold']
            if old is None:
                state={'signature':signature,'stable':1,'track_id':None,'box':d['box'],'surface':None,'surface_stable':0,'motion_frames':0,'recovery':0}
            elif moving:
                count=old.get('motion_frames',0)+1
                state={**old,'signature':signature,'stable':0,'box':d['box'],'motion_frames':count,'recovery':0,
                       'reference':old.get('reference') if old.get('motion_frames',0) else old['signature']}
                # A single exposure/motion spike is held, not treated as proof
                # of departure. Two consecutive moving frames break identity.
                if count>=2:state['track_id']=None
            else:
                box_change=max(abs(d['box'][k]-old['box'][k]) for k in ('x','width'))
                state={**old,'signature':signature,'stable':old['stable']+1,'box':d['box'],'motion_frames':0}
                if old.get('motion_frames',0)==1 or old.get('recovery',0):
                    reference=old.get('reference',old['signature'])
                    change=np.abs(signature-reference)
                    distance=float((np.mean(change[:,:25])+np.mean(change[:,-25:]))/2)
                    if distance<=4 and box_change<.04:
                        state['recovery']=old.get('recovery',0)+1
                        state['stable']=0 if state['recovery']<2 else 2
                        if state['recovery']>=2:state['recovery']=0
                    else:state['track_id']=None;state['stable']=1;state['recovery']=0
                if box_change>=.055:state['track_id']=None;state['stable']=1
            if state['stable']>=2 and state['track_id'] is None:
                self.counter+=1;state['track_id']=f'Vial {self.counter}'
            candidate=d['surface'];previous_surface=old.get('surface') if old else None
            surface_stable=(old.get('surface_stable',0)+1 if old and candidate and previous_surface and abs(candidate['y1']-previous_surface['y1'])<.04 and not moving else 1 if candidate else 0)
            state['surface']=candidate;state['surface_stable']=surface_stable
            if candidate and surface_stable<2:d['surface']=None;d['surface_reason']='SURFACE_CONFIRMATION_PENDING'
            self.slots[name]=state
            status='MOVING' if moving else 'TRACKING' if state['track_id'] and state['stable']>=2 else 'CONFIRMING'
            if status!='TRACKING':d['surface']=None;d['surface_reason']='VIAL_IDENTITY_UNCERTAIN'
            output.append({**d,'track_id':state['track_id'] if status=='TRACKING' else None,'status':status,'motion':motion})
        for name in list(self.slots):
            if name not in present:del self.slots[name]
        self.last_time=seconds
        return {'version':VERSION,'captured_at':seconds,'width':640,'height':480,'detections':output,
                'issues':(['INPUT_GAP_IDENTITY_RESET'] if gap else [])+([] if output else ['NO_SUPPORTED_VIAL_GEOMETRY']),
                'surface_is_physical_volume':False,'recipe_writes':0}
