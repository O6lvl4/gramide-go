from pathlib import Path
import json,subprocess,sys,tempfile,hashlib
checkout=Path(sys.argv[1]).resolve()
root=checkout/'src/go'
binary=Path(__file__).resolve().parents[1]/'gramide_go'
scratch=tempfile.TemporaryDirectory()
oracle=Path(scratch.name)/'oracle'
subprocess.run(['go','build','-o',str(oracle),str(binary.parent/'ci/reference_ranges.go')],check=True)
results={'reference_invalid':[],'gramide_rejected':[],'range_mismatch':[],'passed':[],'symbols':0}
for path in sorted(root.rglob('*.go')):
 if 'testdata' in path.parts:continue
 expected=subprocess.run([str(oracle),str(path)],text=True,capture_output=True)
 if expected.returncode:results['reference_invalid'].append(str(path.relative_to(checkout)));continue
 actual=subprocess.run([str(binary),'symbols',str(path)],text=True,capture_output=True)
 if actual.returncode:results['gramide_rejected'].append({'path':str(path.relative_to(checkout)),'error':actual.stderr});continue
 exp=json.loads(expected.stdout);got=[{k:s[k] for k in ['name','start','end','start_byte','end_byte']} for s in json.loads(actual.stdout)['symbols'] if s['syntax_kind'] in ('function_declaration','method_declaration')]
 if exp!=got:results['range_mismatch'].append({'path':str(path.relative_to(checkout)),'expected':exp,'actual':got})
 else:results['passed'].append(str(path.relative_to(checkout)));results['symbols']+=len(exp)
results['reference_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=checkout,text=True).strip()
results['go_version']=subprocess.check_output(['go','version'],text=True).strip()
results['binary_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
results['input_sha256']={str(p.relative_to(checkout)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*.go')) if 'testdata' not in p.parts}
Path(sys.argv[2]).write_text(json.dumps(results,indent=2)+'\n')
print({k:len(v) if isinstance(v,list) else v for k,v in results.items() if k != 'input_sha256'})
for row in results['gramide_rejected']:print(row)
for row in results['range_mismatch'][:3]:
 print(row['path'])
 for a,b in zip(row['expected'],row['actual']):
  if a!=b:print(a,b);break

sys.exit(1 if results["gramide_rejected"] or results["range_mismatch"] or results["reference_invalid"] else 0)
