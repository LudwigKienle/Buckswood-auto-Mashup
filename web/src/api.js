let token='';
export function setToken(value){token=value;}
export async function api(path, body){
  const options=body===undefined?{}:{method:'POST',headers:{'x-studio-token':token},body};
  if(body!==undefined && !(body instanceof FormData)){
    options.headers['Content-Type']='application/json';options.body=JSON.stringify(body);
  }
  const response=await fetch('/api'+path,options);
  const data=await response.json();
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));
  return data;
}
export const timeLabel=s=>`${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`;
