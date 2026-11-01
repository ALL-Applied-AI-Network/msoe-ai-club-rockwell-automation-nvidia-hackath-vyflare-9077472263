import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {describe,it,expect,vi} from "vitest";
import {Model2ResultView} from "../../client/src/components/Model2ResultView";
import type {Model2Result} from "../../client/src/inspection/model2";
vi.stubGlobal("React",React);
const result={observation:{predicted_recipe_id:41,top_score:0.995,second_recipe_id:7,second_score:0.003,status:"accepted_observation"},verification:{relation:"matches_intended_recipe",flags:["expected_transition_contamination"],note:"Match recorded but not counted.",counts_as_supporting_evidence:false},input_quality:{warnings:[]},model_metadata:{config_version:"model2-baseline-v4",preprocessing_version:"station-crop-v1",accept_threshold:0.9,approved_for_supporting_evidence:false},interpretation:"Not a probability of correctness."} as unknown as Model2Result;
describe("Model2 experimental result presentation",()=>{
 it("does not present a high score as verified identity or clear first-vial review",()=>{const html=renderToStaticMarkup(<Model2ResultView result={result}/>);expect(html).toContain("Not Approved as Supporting Evidence");expect(html).toContain("Uncalibrated Score: 0.9950");expect(html).toContain("expected transition contamination");expect(html).toContain("Recipe matching and creation remain unchanged");expect(html).toContain("No automatic release");expect(html).not.toContain("99.5%");});
 it("shows abstention and mock responses without claiming recipe identification",()=>{const abstain=renderToStaticMarkup(<Model2ResultView result={{...result,observation:{...result.observation!,status:"unknown_uncertain"}}}/>);expect(abstain).toContain("Unknown or Uncertain");const mock=renderToStaticMarkup(<Model2ResultView result={{...result,mock:true,observation:null}}/>);expect(mock).toContain("No Recipe Inference");expect(mock).not.toContain("Top Resemblance:");});
});
