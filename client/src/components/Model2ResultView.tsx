import type { Model2Result } from "../inspection/model2";
export function Model2ResultView({result}:{result:Model2Result}) {
  const observation=result.observation;
  return <section aria-label="Model 2 Experimental Observation"><h3>Model 2 Recipe Resemblance</h3>
    <p className="workspace-warning">{result.model_metadata.approved_for_supporting_evidence ? "Experimental observation; separate quality checks still apply." : "Not Approved as Supporting Evidence · Does Not Verify a Recipe"}</p>
    {result.mock ? <p>Mock Response · No Recipe Inference</p> : observation ? <>
      <p>Top Resemblance: Recipe {observation.predicted_recipe_id}</p><p>Uncalibrated Score: {observation.top_score.toFixed(4)} · Threshold: {result.model_metadata.accept_threshold.toFixed(2)}</p>
      <p>{observation.status === "accepted_observation" ? "Above classifier threshold; this is not a probability of correctness." : "Abstained · Unknown or Uncertain"}</p>
      <p>Next Resemblance: Recipe {observation.second_recipe_id} · Score {observation.second_score.toFixed(4)}</p>
    </> : <p>No classifier observation returned.</p>}
    <p>Comparison: {result.verification.relation.replaceAll("_"," ")}</p><p>{result.verification.note}</p>
    <p>{result.interpretation}</p>
    {result.verification.flags.map(flag=><p className="workspace-warning" key={flag}>{flag.replaceAll("_"," ")}</p>)}
    {result.input_quality.warnings.map(w=><p className="workspace-warning" key={w}>{w}</p>)}
    <p>Recipe matching and creation remain unchanged. Model 2 cannot clear Model 4 or first-vial flags. No automatic release.</p>
    <details><summary>Model 2 Provenance and Scores</summary><p>{result.model_metadata.config_version} · {result.model_metadata.preprocessing_version}</p><pre className="result-json">{JSON.stringify(result,null,2)}</pre></details>
  </section>;
}
