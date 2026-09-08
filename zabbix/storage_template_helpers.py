"""Build deterministic Zabbix dataset items and quota triggers."""
import copy
import uuid


PREFIXES = ("zfs.dataset.used", "zfs.dataset.utilization", "zfs.snapshot.retained", "zfs.snapshot.retained_percent", "zfs.snapshot.oldest_age")


def expand_datasets(document, datasets):
    template = document["zabbix_export"]["templates"][0]
    prototypes = [item for item in template["items"] if item["key"] in {prefix + '["config"]' for prefix in PREFIXES}]
    if len(prototypes) != len(PREFIXES):
        raise ValueError("Storage template is missing dataset prototypes")
    template["items"] = [item for item in template["items"] if not any(item["key"].startswith(prefix + "[") for prefix in PREFIXES)]
    for dataset in datasets:
        for prototype in prototypes:
            item = replace_dataset(copy.deepcopy(prototype), dataset)
            if item["key"].startswith("zfs.dataset.utilization["):
                high = item["triggers"][0]
                expression = 'min(/ZFS by Zabbix agent active/' + item["key"] + ',5m)>=80'
                item["triggers"].append({
                    "uuid": uuid.uuid5(uuid.NAMESPACE_URL, "private-cloud:quota-warning:" + dataset["name"]).hex,
                    "expression": expression,
                    "name": "ZFS dataset " + dataset["name"] + " is over 80% utilized",
                    "priority": "WARNING",
                    "dependencies": [{"name": high["name"], "expression": high["expression"]}],
                })
            template["items"].append(item)


def replace_dataset(value, dataset):
    if isinstance(value, list):
        return [replace_dataset(item, dataset) for item in value]
    if isinstance(value, dict):
        return {key: uuid.uuid5(uuid.NAMESPACE_URL, "private-cloud:" + dataset["name"] + ":" + item).hex if key == "uuid" else replace_dataset(item, dataset) for key, item in value.items()}
    if isinstance(value, str):
        return value.replace("tank/secure/backup/k0s/config", dataset["dataset"]).replace('["config"]', '["' + dataset["name"] + '"]').replace("Dataset config:", "Dataset " + dataset["name"] + ":").replace("dataset config ", "dataset " + dataset["name"] + " ")
    return value
