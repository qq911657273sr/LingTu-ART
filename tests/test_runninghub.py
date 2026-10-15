import unittest
from unittest.mock import patch
from artlib.ai_providers import generate
class RHTests(unittest.TestCase):
 def test_v2_repeat_and_download(self):
  calls=[]; updates=[]
  def req(url,payload=None,headers=None,raw=None):
   calls.append((url,payload,headers))
   if url.endswith('/binary'): return {'code':0,'data':{'fileName':'openapi/ref.png'}}
   if '/run/' in url: return {'taskId':'123','status':'RUNNING'}
   return {'status':'SUCCESS','results':[{'outputType':'png','url':'https://result.example/result.png'}]}
  c={'kind':'runninghub','base_url':'https://www.runninghub.ai','rh_mode':'app','rh_version':'v2','workflow_id':'123','instance_type':'plus','repeat_main':True,'image_nodes':[{'nodeId':'470','fieldName':'image'},{'nodeId':'546','fieldName':'image'}],'prompt_node':{'nodeId':'648','fieldName':'text'},'extra_nodes':[{'nodeId':'13','fieldName':'megapixels','fieldValue':'2.2'}]}
  with patch('artlib.ai_providers.json_request',side_effect=req),patch('artlib.ai_providers.time.sleep'),patch('artlib.ai_providers.read_image',return_value=b'img'):
   self.assertEqual(generate(c,'test-secret','full body',[b'png'],lambda **x:updates.append(x)),b'img')
  self.assertEqual(len(calls),3); nodes=calls[1][1]['nodeInfoList']; self.assertEqual(nodes[1]['fieldValue'],nodes[2]['fieldValue']); self.assertEqual(calls[1][1]['instanceType'],'plus'); self.assertEqual(updates[1]['remote_id'],'123')
 def test_text_only_v1(self):
  calls=[]
  def req(url,payload=None,headers=None,raw=None):
   calls.append(payload)
   return {'code':0,'data':{'taskId':'123'}} if url.endswith('/create') else {'code':0,'data':[{'fileType':'png','fileUrl':'https://result.example/x.png'}]}
  c={'kind':'runninghub','base_url':'https://www.runninghub.ai','workflow_id':'123','image_nodes':[],'prompt_node':{'nodeId':'51','fieldName':'text'}}
  with patch('artlib.ai_providers.json_request',side_effect=req),patch('artlib.ai_providers.time.sleep'),patch('artlib.ai_providers.read_image',return_value=b'img'):
   generate(c,'test-secret','landscape',[],lambda **x:None)
  self.assertEqual(len(calls[0]['nodeInfoList']),1)
 def test_failed_no_retry(self):
  c={'kind':'runninghub','base_url':'https://www.runninghub.ai','rh_version':'v2','workflow_id':'123','image_nodes':[],'prompt_node':{'nodeId':'51','fieldName':'text'}}
  with patch('artlib.ai_providers.json_request',return_value={'taskId':'123','status':'FAILED','errorMessage':'test-secret'}) as req:
   with self.assertRaisesRegex(ValueError,'密钥已隐藏'):generate(c,'test-secret','x',[],lambda **x:None)
   self.assertEqual(req.call_count,1)
if __name__=='__main__':unittest.main()
