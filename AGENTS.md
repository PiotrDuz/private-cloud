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
 - each service has its own dataset under backup/k0s/services or no-backup/k0s/services, with backup as the default
 - each servcie has a dedicated 10Ti PV so it does not need extension
 - each dataset for kubernetes service should have a quota
