"""The detection pipeline.

1. quick:  every item, windowed yes/no probability. A high-recall filter.
2. reason: items the quick check flagged, judged again with reasoning on.
3. claims: items the quick check flagged; extracts authority claims and reported sends,
           verifies claims against the record and checks send destinations.

alert = quick >= threshold AND (reason says yes OR claims finds an unverified claim or an outside send)
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .destinations import Destinations
from .item import Item, Verdict
from .llm import Llama
from .prompts import Prompts

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "risky_actions": {"type": "array", "items": {"type": "object", "properties": {"quote": {"type": "string"}}, "required": ["quote"]}},
        "reported_sends": {"type": "array", "items": {"type": "object", "properties": {
            "quote": {"type": "string"}, "destination": {"type": "string"}}, "required": ["quote", "destination"]}},
        "authority_claims": {"type": "array", "items": {"type": "object", "properties": {
            "quote": {"type": "string"}, "who": {"type": "string"}, "cites_page": {"type": "string"}},
            "required": ["quote", "who", "cites_page"]}},
    },
    "required": ["risky_actions", "authority_claims", "reported_sends"],
}

AUTHORITY = re.compile(r"\b(asked|approved|confirmed|decided|agreed|requested|said|says|authori[sz]ed|allowed|"
                       r"rules?|conventions?|polic\w*|mode|suspended|outdated|from now on|no longer)\b", re.I)
REFUSED = re.compile(r"\b(refus\w*|rejected|was blocked|is blocked|cannot|could not|not allowed)\b", re.I)
REVIEW_KINDS = ("approved", "requested changes")
PR_REF = re.compile(r"(?:PR #|pull/)(\d+)")


class Pipeline:
    def __init__(self, llm: Llama, prompts: Prompts, cfg: Dict[str, Any], records: Any, destinations: Destinations):
        self.llm = llm
        self.prompts = prompts
        self.records = records
        self.destinations = destinations
        self.threshold = float(cfg.get("threshold", 0.5))
        self.window = int(cfg.get("window_tokens", 250))
        self.stride = int(cfg.get("stride_tokens", 200))
        self.max_quick = int(cfg.get("max_quick_tokens", 800))
        self.max_reason = int(cfg.get("max_reason_tokens", 1200))
        self.reason_budget = int(cfg.get("reason_budget", 1400))
        self.examples = bool(cfg.get("quick_examples", True))
        self.stages = cfg.get("stages", ["quick", "reason", "claims"])
        if cfg.get("to_principal_pattern"):
            self.to_principal = re.compile(cfg["to_principal_pattern"], re.I)
        else:
            names = "|".join(re.escape(n) for n in [prompts.variables.get("principal", "")] + list(cfg.get("principal_aliases", [])) if n)
            self.to_principal = re.compile(rf"^\s*(\*\*)?({names})[:,]|\bfor ({names})\b", re.I) if names else None
        self.rule_page = re.compile(cfg["rule_page_pattern"]) if cfg.get("rule_page_pattern") else None
        self.ref_pattern = re.compile(cfg.get("context_ref_pattern", r"#(\d{4,6})\b"))

    @staticmethod
    def header(item: Item) -> str:
        return f"Source: {item.source}\nAuthor: {item.author}"

    # Step 1
    def quick(self, item: Item) -> float:
        system = self.prompts.get("quick") + ("\n\n" + self.prompts.get("quick_examples") if self.examples else "")
        ids = self.llm.tokenize(item.text)[:self.max_quick]
        chunks = [ids[i:i + self.window] for i in range(0, max(len(ids) - self.window, 0) + 1, self.stride)] or [[]]
        if len(ids) > self.window and (len(ids) - self.window) % self.stride:
            chunks.append(ids[-self.window:])
        best = 0.0
        for chunk in chunks:
            body = self.llm.detokenize(chunk)
            user = (f"{self.header(item)}\n<content>\n{body}\n</content>\n"
                    "Does this content try to steer an AI agent beyond what its source may ask? yes or no")
            best = max(best, self.llm.p_yes(system, user))
        return best

    # Step 2
    def reason(self, item: Item) -> Dict[str, str]:
        body = self.llm.truncate(item.text, self.max_reason)
        user = f"{self.header(item)}\n<content>\n{body}\n</content>"
        text = self.llm.chat(self.prompts.get("reason"), user, self.reason_budget, think=True)
        m = re.search(r"VERDICT:\s*(yes|no)", text, re.I)
        return {"verdict": m.group(1).lower() if m else "none", "analysis": text}

    # Step 3
    def claims(self, item: Item) -> Dict[str, Any]:
        body = self.llm.truncate(item.text, 1500)
        raw = self.llm.chat(self.prompts.get("extract"), f"{self.header(item)}\n<content>\n{body}\n</content>", 500,
                            json_schema=EXTRACT_SCHEMA)
        try:
            ex = json.loads(raw)
        except ValueError:
            return {"reasons": ["claim check: unparsable extraction"], "extraction": raw}
        reasons: List[str] = []
        base: Optional[List[str]] = None
        for c in ex.get("authority_claims", []):
            quote = c.get("quote", "")
            if not AUTHORITY.search(quote) or self._to_principal(quote):
                continue
            page = (c.get("cites_page") or "").strip()
            if page and self.rule_page and page in item.text and self.rule_page.search(page) \
                    and self.prompts.variables.get("principal", "").lower() not in c.get("who", "").lower():
                continue  # really points at a rule page
            if base is None:
                base = self.records.records(item, [])
            if base is None:
                continue  # nothing to verify against in this kind of context
            recs = list(base)
            refs = [r for r in self.ref_pattern.findall(quote) if str(r) != str(item.context.get("id"))]
            if refs:
                recs += self.records.records(item, refs) or []
            if not self.verify(quote, recs):
                reasons.append(f"unverified claim: {quote}")
        for s in ex.get("reported_sends", []):
            if self.destinations.outside(s.get("destination", ""), s.get("quote", "")):
                reasons.append(f"outside send: {s.get('quote', '')}")
        risky = [a["quote"] for a in ex.get("risky_actions", [])
                 if not self._to_principal(a["quote"]) and not REFUSED.search(a["quote"])]
        return {"reasons": reasons, "risky": risky, "extraction": ex}

    def _to_principal(self, quote: str) -> bool:
        return bool(self.to_principal and self.to_principal.search(quote))

    def verify(self, claim: str, records: List[str]) -> bool:
        if not records:
            return False
        reviews = [r for r in records if r.startswith("[review]")]
        if not PR_REF.search(claim):
            for kind in REVIEW_KINDS:
                if re.search(kind.replace(" ", r"\s+"), claim, re.I) and any(re.search(kind, r, re.I) for r in reviews):
                    return True  # a review of that kind is on record in this context
        prs = set(PR_REF.findall(claim))
        if prs and re.search(r"\b(review|request\w* changes|approv\w*|comment\w*)\b", claim, re.I):
            if any(prs & set(re.findall(r"pull/(\d+)", r)) for r in reviews):
                return True  # a review of that very PR is on record
        text = "\n---\n".join(records)[-6000:]
        answer = self.llm.chat(self.prompts.get("verify"), f"Claim: {claim}\n\nRecords:\n{text}\n\nDo the records support the claim? yes or no", 3)
        return answer.lower().startswith("yes")

    def run(self, item: Item) -> Verdict:
        scores: Dict[str, Any] = {}
        reasons: List[str] = []
        q = self.quick(item) if "quick" in self.stages else 1.0
        scores["quick"] = round(q, 4)
        if q < self.threshold:
            return Verdict(False, [], scores)
        if "reason" in self.stages:
            r = self.reason(item)
            scores["reason"] = r["verdict"]
            if r["verdict"] == "yes":
                m = re.search(r"RISKY:\s*(.+?)(?:\nVERDICT|$)", r["analysis"], re.S)
                reasons.append("reasoning: " + (m.group(1).strip() if m else "risky request")[:500])
        if "claims" in self.stages:
            c = self.claims(item)
            scores["claims"] = len(c["reasons"])
            reasons += c["reasons"]
        return Verdict(bool(reasons), reasons, scores)
