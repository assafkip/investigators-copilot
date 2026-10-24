"""GreyNoise community API: is this IP mass-scanner noise, a known-good service, or unseen? T3.

Ported from assafkip/kipi investigations/enrich/greynoise.py. Needs a free
$GREYNOISE_API_KEY. A 404 is GreyNoise's documented "not observed" answer and is
reported as classification `unseen`, not as a failure.
"""
from __future__ import annotations

from . import _common as c
from .base import Adapter

_API = "https://api.greynoise.io/v3/community/"


class GreyNoiseAdapter(Adapter):
    slug = "greynoise"
    display_name = "GreyNoise community (scanner classification)"
    env_var = "GREYNOISE_API_KEY"
    signup_url = "https://viz.greynoise.io/signup"
    category = "reputation"
    tier = "T3"
    keyless = False
    watched_types = ("ip",)

    def run(self, query, mode=None, timeout=30):
        ip = c.require_ip(query, "greynoise")
        key = self.get_key()
        data = c.get_json(_API + ip, timeout=timeout, headers={"key": key}, empty_on=(404,))
        if data is None:
            data = {"ip": ip, "noise": False, "riot": False, "classification": "unseen"}
        cls = data.get("classification", "unknown")
        summary = (f"classification: {cls}\nmass-scanner noise: {data.get('noise')}\n"
                   f"known-good service (RIOT): {data.get('riot')}\nname: {data.get('name') or '(none)'}")
        return [c.res(self, "document", f"GreyNoise: {ip} -- {cls}", summary,
                      url=f"https://viz.greynoise.io/ip/{ip}", raw_json=data, confidence="medium")]
