Writing documentation rules: 
1. In lists/ bullet points try to use single, short sentences to show the intent. Avoid writing additional explanations.






Writing scripts rules:
1. Do not write usage echo. Scripts will have documentation in other parts, keep script lean without not needed details that may bloat reading.
2. Do not write tests
3. Do not write dry--runs. Run only requested functionality
4. Use python fro scripts
5. Place helpers in separate files. Reuse helpers from different folders, place them in top level then.
6. Top level methods should be the ones handling main logic, then script should place less important methods on bottom on file. Class definitions on bottom. Top method should be procedural, list steps and show the flow in code.
7. Do not place excessive prints. The script should be ready to self-check and return a result to be ingested by parent script that gathers all the scirpts and runs them in order.

Kubernetess services rules:
 - each service has its own dataset which sits either under services-backed, or under services-no-backup dataset (default is services-backed unless otherwise stated)
 - each servcie has dedicated PV which has a large capacity (like 10TB). so i doesnt have to be extended. The zs dataset quota is keeping the size in check
 - each dataset for kubernetes service should have a quota 