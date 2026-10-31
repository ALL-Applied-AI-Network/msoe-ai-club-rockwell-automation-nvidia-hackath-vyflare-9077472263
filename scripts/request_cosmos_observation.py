"""Optional evidence client for the reference Model 4 integration backend."""
import argparse
import json
import uuid
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from cosmos_companion import validate_context,combine_with_model4

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',default='http://127.0.0.1:7866');p.add_argument('--context',type=Path,required=True)
    p.add_argument('--media',type=Path,required=True);p.add_argument('--model4-result',type=Path)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    try:
        if args.output.exists():raise ValueError('Choose a new output path; overwrite refused')
        context=validate_context(json.loads(args.context.read_text(encoding='utf-8-sig')))
        if args.media.stat().st_size>99*1024*1024:raise ValueError('Use media below 99 MiB to allow multipart overhead')
        boundary='companion-'+uuid.uuid4().hex
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="context"\r\n\r\n'+json.dumps(context)+'\r\n'
              f'--{boundary}\r\nContent-Disposition: form-data; name="media"; filename="input{args.media.suffix.lower()}"\r\n'
              'Content-Type: application/octet-stream\r\n\r\n').encode()+args.media.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
        req=Request(args.url.rstrip('/')+'/v1/cosmos/observe',data=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary})
        with urlopen(req,timeout=300) as response:record=json.load(response)
        if args.model4_result:record=combine_with_model4(record,json.loads(args.model4_result.read_text(encoding='utf-8-sig')))
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(record,indent=2,allow_nan=False),encoding='utf-8')
        print(args.output)
    except (ValueError,OSError,HTTPError,URLError) as error:p.error(str(error))

if __name__=='__main__':main()
