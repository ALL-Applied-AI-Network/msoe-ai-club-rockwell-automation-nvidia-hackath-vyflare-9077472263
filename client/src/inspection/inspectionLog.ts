export type InspectionEvent = { id:string;at:number;kind:"flow"|"timing"|"color"|"recipe"|"held";vial:string;title:string;detail:string;provenance:string };
export function eventsAt(events:InspectionEvent[], seconds:number) {
  return events.filter(e=>Number.isFinite(e.at)&&e.at>=0&&e.at<=seconds).sort((a,b)=>a.at-b.at||a.id.localeCompare(b.id));
}
export function synchronizeLog(previous:InspectionEvent[],events:InspectionEvent[],seconds:number,playing:boolean,seeked=false) {
  if(!playing&&!seeked)return previous;
  const next=eventsAt(events,seconds);
  return next.length===previous.length&&next.every((e,i)=>e.id===previous[i].id&&e.detail===previous[i].detail)?previous:next;
}
