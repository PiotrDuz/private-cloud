"""Derive pod restart revisions from credentials that never reach the cluster."""

import hashlib
import hmac


class FilterModule:
    def filters(self):
        return {"private_cloud_hmac": private_cloud_hmac}


def private_cloud_hmac(value, key):
    return hmac.new(str(key).encode(), str(value).encode(), hashlib.sha256).hexdigest()
