import {useEffect,useState} from "react";
import {readResponse} from "./types";
export function useRecordingSource(installedId:string|undefined,file:File|null) {
  const [registered,setRegistered]=useState<{file:File;id:string;sha:string}|null>(null),[error,setError]=useState("");
  const [retry,setRetry]=useState(0);
  useEffect(()=>{
    setError(""); if(!file)return;
    const controller=new AbortController();
    if(file.size>128*1024*1024){setError("Recording exceeds 128 MiB. Choose a shorter recording.");return;}
    const type=file.type==="video/x-m4v"?"video/mp4":file.type || (/\.mov$/i.test(file.name)?"video/quicktime":"video/mp4");
    fetch("/api/recorded-observer/recordings",{method:"POST",headers:{"Content-Type":type,"X-Recording-Name":encodeURIComponent(file.name)},body:file,signal:controller.signal})
      .then(readResponse<{video_id:string;sha256:string}>).then(r=>{if(!controller.signal.aborted)setRegistered({file,id:r.video_id,sha:r.sha256});})
      .catch(e=>{if(!controller.signal.aborted)setError(e.message);});
    return ()=>controller.abort();
  },[file,retry]);
  return {id:file?(registered?.file===file?registered.id:undefined):installedId,error,
    registering:!!file&&registered?.file!==file&&!error,retry:()=>setRetry(n=>n+1)};
}
