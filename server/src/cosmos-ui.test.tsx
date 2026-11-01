import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe,expect,it,vi } from "vitest";
import { CosmosPanel } from "../../client/src/components/CosmosPanel";
import { validateCosmosResponse } from "../../client/src/inspection/cosmos";
vi.stubGlobal("React",React);
const valid={frame_id:"frame-a",model:"cosmos_full",mode:"real",inference_ms:7,result:{text:"Test description"}};
describe("Cosmos source and result contract",()=>{
 it("accepts only the captured frame and requested route",()=>{
  expect(validateCosmosResponse(valid,"frame-a","cosmos_full").result.text).toBe("Test description");
  for(const change of [{frame_id:"different"},{model:"cosmos"},{mode:"mock"},{result:{mock:true,text:"fake"}},{result:{text:""}},{inference_ms:NaN}])expect(()=>validateCosmosResponse({...valid,...change},"frame-a","cosmos_full")).toThrow();
 });
 it("explains missing Cosmos configuration rather than displaying inference",()=>{
  const html=renderToStaticMarkup(<CosmosPanel media={{current:null}} sourceLabel="Video 1" health={{available:true,mode:"real",models:["measurements"]}} mediaReady={false} disabled={false} refresh={()=>{}}/>);
  expect(html).toContain("Cosmos is not configured");expect(html).toContain("not the video sequence");expect(html).toContain("do not assign recipes");expect(html).not.toContain("Cosmos Observation</h3>");
 });
 it("labels mock mode and disables inference",()=>{
  const html=renderToStaticMarkup(<CosmosPanel media={{current:null}} sourceLabel="Video 1" health={{available:true,mode:"mock",models:["cosmos_full"]}} mediaReady={true} disabled={false} refresh={()=>{}}/>);
  expect(html).toContain("Mock mode — no Cosmos inference");expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Ask Cosmos/);
 });
});
