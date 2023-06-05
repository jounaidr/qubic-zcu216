import json
import sys
import re
import imp
jname=sys.argv[1]
with open(jname) as fjson:
	cfg=json.load(fjson)

wiremap = imp.load_source("wiremap",sys.argv[2])
lor=wiremap.lor
loq=wiremap.loq
for qname,qdict in cfg['Qubits'].items():
	if re.match('Q\d+',qname):
		for fname,fval in qdict.items():
			if fname=='readfreq':
				cfg['Qubits'][qname][fname]+=lor
			elif fname=='freq' or fname=='freq_ef':
				cfg['Qubits'][qname][fname]+=loq

with open(jname,'w') as fjson:
	json.dump(cfg,fjson,indent=4)

#print(json.dumps(cfg,indent=4))
print('lor',lor,'loq',loq)
