import type { Recipe } from "../../../shared/domain";

export function RecipeComposition({ recipe }: { recipe: Recipe }) {
  const parts = [
    { id: "T100", value: recipe.t100Ml, className: "tank--clear" },
    { id: "T200", value: recipe.t200Ml, className: "tank--orange" },
    { id: "T400", value: recipe.t400Ml, className: "tank--blue" }
  ];
  return <div className="composition">
    <div className="composition__bar" aria-hidden="true">
      {parts.filter((p) => p.value).map((part) => <span key={part.id} className={part.className} style={{ flex: part.value ?? 0 }} />)}
    </div>
    <div className="composition__legend">
      {parts.map((part) => <span key={part.id}><i className={part.className} />{part.id} <strong>{part.value ?? 0} mL</strong></span>)}
    </div>
  </div>;
}
