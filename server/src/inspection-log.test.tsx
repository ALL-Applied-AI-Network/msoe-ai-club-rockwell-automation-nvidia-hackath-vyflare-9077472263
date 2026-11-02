import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {describe,it,expect,vi} from "vitest";
import {eventsAt,synchronizeLog,type InspectionEvent} from "../../client/src/inspection/inspectionLog";
import {InspectionLog} from "../../client/src/components/InspectionLog";
vi.stubGlobal("React",React);
const e=(id:string,at:number,title="Observed"):InspectionEvent=>({id,at,kind:"recipe",vial:"Vial 1",title,detail:"Evidence",provenance:"FRESH_RECORDED_VIDEO_OBSERVATION"});
describe("Playback-linked automatic inspection log",()=>{
 it("hides future outcomes and removes them on backward seeks",()=>{const events=[e("a",10),e("b",30)];expect(eventsAt(events,15).map(e=>e.id)).toEqual(["a"]);expect(synchronizeLog(events,events,5,false,true)).toEqual([]);});
 it("freezes incoming entries while paused, even if backend finishes past evidence",()=>{const before=[e("a",5)],later=[...before,e("b",8),e("c",40)];expect(synchronizeLog(before,later,10,false)).toBe(before);expect(synchronizeLog(before,later,10,true).map(e=>e.id)).toEqual(["a","b"]);});
 it("does not duplicate entries on repeated polling or replay",()=>{const events=[e("a",5)];expect(synchronizeLog(events,[...events],10,true)).toBe(events);expect(eventsAt(events,10)).toHaveLength(1);});
 it("does not render model forms, processing buttons or future recipes on initial render",()=>{const observer={job:{state:"completed",progress:100,events:[e("future",60,"Discovered Recipe 999")],assessments:[]},status:{available:true,enabled:true},busy:false,error:"",start:async()=>{},reload:()=>{}};const html=renderToStaticMarkup(<InspectionLog observer={observer as never} currentTime={0} playing={false} seekRevision={0} sourceKey="video-3" started={false} registrationError="" registering={false} retryUpload={()=>{}}/>);expect(html).toContain("Inspection Log");expect(html).not.toContain("Discovered Recipe 999");expect(html).not.toContain("Process Recording");expect(html).not.toContain("Comparison Recipe");});
});
