"""Validate using the actual reference branch's RemoteCosmosModel class."""
import argparse,importlib.util,json,os,subprocess,sys
from pathlib import Path
from unittest.mock import patch

p=argparse.ArgumentParser();p.add_argument('--url');p.add_argument('--image');p.add_argument('--output',required=True)
args=p.parse_args()
root=Path.cwd();snapshot=root/'.local-tools/model4-reference-client';snapshot.mkdir(exist_ok=True)
reference='origin/model4/recipe-detection-backend-integration'
source=subprocess.check_output(['git','show',reference+':backend/models.py'])
(snapshot/'models.py').write_bytes(source)
spec=importlib.util.spec_from_file_location('reference_models',snapshot/'models.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
from PIL import Image
if args.url:
    os.environ['COSMOS_FULL_URL']=args.url
    os.environ['COSMOS_FULL_REMOTE_MODEL']='cosmos'
    with Image.open(args.image) as image:result=module.RemoteCosmosModel().predict(image.convert('RGB'),'Describe the visible liquid color in this vial. Do not infer recipe, chemical identity or measured volume.')
else:
    sys.path.insert(0,str(root/'scripts'))
    from serve_spark_adapter import create_app
    import io,tempfile
    class Runtime:
        identity={'adapter':'contract-fixture'}
        execution={'hostname':'fixture-dgx','system':'Linux','machine':'aarch64','gpu':'NVIDIA GB10'}
        def predict(self,path,mode,prompt_override=None):
            self.prompt=prompt_override
            return dict(outputs={'adapter':dict(raw_text='A green liquid.',parsed=None)})
    runtime=Runtime()
    with tempfile.TemporaryDirectory() as folder:
        app=create_app(runtime,Path(folder));client=app.test_client()
        class Response(io.BytesIO):
            def __enter__(self):return self
            def __exit__(self,*args):self.close()
        def transport(request,**kwargs):
            response=client.post('/backend/predict',data=request.data,headers=dict(request.header_items()))
            if response.status_code!=200:raise RuntimeError(response.get_data(as_text=True))
            return Response(response.data)
        with patch.object(module.request,'urlopen',side_effect=transport):
            result=module.RemoteCosmosModel().predict(Image.new('RGB',(32,24),'green'),'Contract prompt µ')
        assert runtime.prompt=='Contract prompt µ'
        assert result['text']=='A green liquid.'
result=dict(reference_commit=subprocess.check_output(['git','rev-parse',reference]).decode().strip(),
            actual_reference_client_used=True,live=args.url is not None,result=result)
out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
if out.exists():raise ValueError('Choose new output')
out.write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
